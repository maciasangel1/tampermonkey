"""Session-manager sidebar for FedoRT.

Provides a SecureCRT-style tree of saved sessions organised in folders,
with search/filter, quick-connect, drag-and-drop reordering, and a
right-click context menu.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, GObject, Gtk, Pango

from fedort.settings import SSHSession

logger = logging.getLogger(__name__)

# ── Icon look-up table ──────────────────────────────────────────────────
_FOLDER_ICON = "folder"
_PROTOCOL_ICONS: dict[str, str] = {
    "ssh2": "network-server",
    "telnet": "network-workgroup",
    "serial": "media-removable",
    "raw": "network-transmit",
    "rlogin": "network-server",
}
_DEFAULT_SESSION_ICON = "network-server"

# Default folder names that are created automatically.
_DEFAULT_FOLDERS: list[str] = ["Default", "SSH", "Telnet", "Serial"]

# TreeStore column indices.
COL_ICON = 0
COL_NAME = 1
COL_SESSION_DATA = 2
COL_IS_FOLDER = 3
COL_PROTOCOL = 4


def _resolve_icon(icon_name: str, size: int = 16) -> Optional[GdkPixbuf.Pixbuf]:
    """Load a themed icon, falling back to *None* if the name is missing."""
    theme = Gtk.IconTheme.get_default()
    try:
        return theme.load_icon(icon_name, size, Gtk.IconLookupFlags.USE_BUILTIN)
    except GLib.Error:
        return None


class SessionSidebar(Gtk.Box):
    """Left-hand sidebar listing saved sessions in a tree.

    Signals
    -------
    session-activated (SSHSession)
        Emitted when the user double-clicks a session or presses Enter.
    session-connect  (str, int, str)
        Emitted from the Quick Connect bar (hostname, port, username).
    """

    __gsignals__ = {
        "session-activated": (
            GObject.SignalFlags.RUN_LAST,
            None,
            (GObject.TYPE_PYOBJECT,),
        ),
        "session-connect": (
            GObject.SignalFlags.RUN_LAST,
            None,
            (GObject.TYPE_STRING, GObject.TYPE_INT, GObject.TYPE_STRING),
        ),
    }

    # ── construction ────────────────────────────────────────────────────

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_border_width(4)

        # Mapping from folder name → TreeIter for quick look-up.
        self._folder_iters: dict[str, Gtk.TreeIter] = {}

        # Keep references to menus so they are not garbage-collected.
        self._context_menu: Optional[Gtk.Menu] = None

        self._build_search_bar()
        self._build_quick_connect()
        self._build_tree_view()
        self._build_action_buttons()
        self._create_default_folders()

    # ── search / filter bar ─────────────────────────────────────────────

    def _build_search_bar(self) -> None:
        """Add a search entry at the top of the sidebar."""
        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Filter sessions\u2026")
        self._search_entry.connect("search-changed", self._on_search_changed)
        self.pack_start(self._search_entry, expand=False, fill=True, padding=0)

    # ── quick-connect bar ───────────────────────────────────────────────

    def _build_quick_connect(self) -> None:
        """Hostname entry + Connect button."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        self._quick_entry = Gtk.Entry()
        self._quick_entry.set_placeholder_text("user@host:port")
        self._quick_entry.connect("activate", self._on_quick_connect)
        box.pack_start(self._quick_entry, expand=True, fill=True, padding=0)

        btn = Gtk.Button(label="Connect")
        btn.connect("clicked", self._on_quick_connect)
        box.pack_start(btn, expand=False, fill=False, padding=0)

        self.pack_start(box, expand=False, fill=True, padding=0)

    # ── tree view ───────────────────────────────────────────────────────

    def _build_tree_view(self) -> None:
        """Construct the TreeStore, filter model, and TreeView."""
        # icon (Pixbuf), name (str), session_data (JSON str),
        # is_folder (bool), protocol_type (str)
        self._store = Gtk.TreeStore(
            GdkPixbuf.Pixbuf, str, str, bool, str,
        )

        # Wrap in a filter model for search.
        self._filter_model = self._store.filter_new()
        self._filter_model.set_visible_func(self._filter_func)

        self._tree = Gtk.TreeView(model=self._filter_model)
        self._tree.set_headers_visible(False)
        self._tree.set_enable_tree_lines(True)
        self._tree.set_reorderable(True)

        # Single column: icon + text.
        col = Gtk.TreeViewColumn("Sessions")
        icon_cell = Gtk.CellRendererPixbuf()
        text_cell = Gtk.CellRendererText()
        text_cell.set_property("ellipsize", Pango.EllipsizeMode.END)
        col.pack_start(icon_cell, expand=False)
        col.pack_start(text_cell, expand=True)
        col.add_attribute(icon_cell, "pixbuf", COL_ICON)
        col.add_attribute(text_cell, "text", COL_NAME)
        self._tree.append_column(col)

        # Signals.
        self._tree.connect("row-activated", self._on_row_activated)
        self._tree.connect("button-press-event", self._on_button_press)
        self._tree.connect("key-press-event", self._on_key_press)

        # Drag-and-drop (already enabled via set_reorderable, but we also
        # allow cross-folder moves via internal DnD).
        self._tree.enable_model_drag_source(
            Gdk.ModifierType.BUTTON1_MASK,
            [Gtk.TargetEntry.new("GTK_TREE_MODEL_ROW", Gtk.TargetFlags.SAME_WIDGET, 0)],
            Gdk.DragAction.MOVE,
        )
        self._tree.enable_model_drag_dest(
            [Gtk.TargetEntry.new("GTK_TREE_MODEL_ROW", Gtk.TargetFlags.SAME_WIDGET, 0)],
            Gdk.DragAction.MOVE,
        )

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self._tree)
        self.pack_start(scroll, expand=True, fill=True, padding=0)

    # ── bottom action buttons ───────────────────────────────────────────

    def _build_action_buttons(self) -> None:
        """New Session / New Folder / Delete buttons."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        for label, callback in (
            ("New Session", self._on_new_session),
            ("New Folder", self._on_new_folder),
            ("Delete", self._on_delete),
        ):
            btn = Gtk.Button(label=label)
            btn.connect("clicked", callback)
            box.pack_start(btn, expand=True, fill=True, padding=0)

        self.pack_start(box, expand=False, fill=True, padding=0)

    # ── default folders ─────────────────────────────────────────────────

    def _create_default_folders(self) -> None:
        """Ensure the default folder nodes exist in the tree."""
        for name in _DEFAULT_FOLDERS:
            if name not in self._folder_iters:
                self.add_folder(name)

    # ── public API ──────────────────────────────────────────────────────

    def load_sessions(self, sessions: list[SSHSession]) -> None:
        """Populate the tree from a list of *SSHSession* objects.

        Existing rows are cleared first.  Folders are created on the fly
        when a session references a folder name that does not yet exist.

        Parameters
        ----------
        sessions:
            Flat list of SSHSession instances to display.
        """
        self._store.clear()
        self._folder_iters.clear()
        self._create_default_folders()

        for session in sessions:
            self.add_session(session)

        self._tree.expand_all()

    def get_selected_session(self) -> Optional[SSHSession]:
        """Return the currently highlighted *SSHSession*, or *None*.

        Returns
        -------
        SSHSession or None
            The session data for the selected row, or *None* if no
            session row is selected (e.g. a folder is selected).
        """
        sel = self._tree.get_selection()
        model, tree_iter = sel.get_selected()
        if tree_iter is None:
            return None
        if model[tree_iter][COL_IS_FOLDER]:
            return None
        return self._session_from_iter(model, tree_iter)

    def refresh(self) -> None:
        """Reload sessions from the on-disk settings manager.

        Imports *SettingsManager* lazily to avoid circular imports.
        """
        from fedort.settings import SettingsManager

        mgr = SettingsManager()
        self.load_sessions(mgr.load_sessions())

    def add_session(self, session: SSHSession) -> Gtk.TreeIter:
        """Insert a single session into the tree under its folder.

        Parameters
        ----------
        session:
            The session to add.

        Returns
        -------
        Gtk.TreeIter
            Iterator pointing to the newly inserted row.
        """
        folder_name = session.folder or "Default"
        parent = self._ensure_folder(folder_name)
        icon_name = _PROTOCOL_ICONS.get(session.protocol, _DEFAULT_SESSION_ICON)
        icon = _resolve_icon(icon_name)
        data = json.dumps(asdict(session))
        display_name = session.session_name or session.hostname or "(unnamed)"
        return self._store.append(
            parent,
            [icon, display_name, data, False, session.protocol],
        )

    def add_folder(self, name: str, parent: Optional[Gtk.TreeIter] = None) -> Gtk.TreeIter:
        """Create a new folder node in the tree.

        Parameters
        ----------
        name:
            Display name for the folder.
        parent:
            Optional parent folder iterator for nested folders.

        Returns
        -------
        Gtk.TreeIter
            Iterator pointing to the newly created folder row.
        """
        icon = _resolve_icon(_FOLDER_ICON)
        tree_iter = self._store.append(parent, [icon, name, "", True, ""])
        self._folder_iters[name] = tree_iter
        return tree_iter

    # ── internal helpers ────────────────────────────────────────────────

    def _ensure_folder(self, name: str) -> Gtk.TreeIter:
        """Return the TreeIter for *name*, creating the folder if needed."""
        if name not in self._folder_iters:
            self.add_folder(name)
        return self._folder_iters[name]

    @staticmethod
    def _session_from_iter(
        model: Gtk.TreeModel, tree_iter: Gtk.TreeIter,
    ) -> Optional[SSHSession]:
        """Deserialise the JSON blob stored in *COL_SESSION_DATA*."""
        raw: str = model[tree_iter][COL_SESSION_DATA]
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return SSHSession(**{
                k: v for k, v in data.items()
                if k in SSHSession.__dataclass_fields__
            })
        except (json.JSONDecodeError, TypeError):
            logger.exception("Failed to deserialise session data")
            return None

    @staticmethod
    def _parse_quick_connect(text: str) -> tuple[str, int, str]:
        """Parse ``user@host:port`` into *(hostname, port, username)*.

        Missing parts fall back to ``("", 22, "")``.
        """
        username = ""
        port = 22
        host = text.strip()

        if "@" in host:
            username, host = host.split("@", 1)
        if ":" in host:
            host, port_str = host.rsplit(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                port = 22
        return host, port, username

    # ── filter ──────────────────────────────────────────────────────────

    def _filter_func(
        self,
        model: Gtk.TreeModel,
        tree_iter: Gtk.TreeIter,
        _data: Any = None,
    ) -> bool:
        """Return *True* if the row should be visible given the search term."""
        query = self._search_entry.get_text().strip().lower()
        if not query:
            return True

        # Folders are visible when any child matches.
        if model[tree_iter][COL_IS_FOLDER]:
            return self._folder_has_visible_child(model, tree_iter, query)

        name: str = (model[tree_iter][COL_NAME] or "").lower()
        raw: str = model[tree_iter][COL_SESSION_DATA] or ""

        if query in name:
            return True

        # Also match on hostname inside the JSON data.
        try:
            data = json.loads(raw)
            hostname = data.get("hostname", "").lower()
            if query in hostname:
                return True
        except (json.JSONDecodeError, TypeError):
            pass
        return False

    def _folder_has_visible_child(
        self,
        model: Gtk.TreeModel,
        parent_iter: Gtk.TreeIter,
        query: str,
    ) -> bool:
        """Recursively check whether *parent_iter* has a visible descendant."""
        n_children = model.iter_n_children(parent_iter)
        for i in range(n_children):
            child = model.iter_nth_child(parent_iter, i)
            if child is None:
                continue
            if model[child][COL_IS_FOLDER]:
                if self._folder_has_visible_child(model, child, query):
                    return True
            else:
                name = (model[child][COL_NAME] or "").lower()
                if query in name:
                    return True
                raw = model[child][COL_SESSION_DATA] or ""
                try:
                    data = json.loads(raw)
                    if query in data.get("hostname", "").lower():
                        return True
                except (json.JSONDecodeError, TypeError):
                    pass
        return False

    # ── signal handlers ─────────────────────────────────────────────────

    def _on_search_changed(self, _entry: Gtk.SearchEntry) -> None:
        self._filter_model.refilter()

    def _on_quick_connect(self, _widget: Gtk.Widget) -> None:
        text = self._quick_entry.get_text()
        if not text.strip():
            return
        host, port, user = self._parse_quick_connect(text)
        if host:
            self.emit("session-connect", host, port, user)

    def _on_row_activated(
        self,
        _tree: Gtk.TreeView,
        path: Gtk.TreePath,
        _col: Gtk.TreeViewColumn,
    ) -> None:
        """Handle double-click / Enter on a tree row."""
        model = self._tree.get_model()
        tree_iter = model.get_iter(path)
        if model[tree_iter][COL_IS_FOLDER]:
            # Toggle expand/collapse for folders.
            if self._tree.row_expanded(path):
                self._tree.collapse_row(path)
            else:
                self._tree.expand_row(path, False)
            return
        session = self._session_from_iter(model, tree_iter)
        if session is not None:
            self.emit("session-activated", session)

    def _on_key_press(self, _widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        """Delete key removes the selected row."""
        if event.keyval == Gdk.KEY_Delete:
            self._on_delete(None)
            return True
        return False

    def _on_button_press(self, _widget: Gtk.Widget, event: Gdk.EventButton) -> bool:
        """Show the context menu on right-click."""
        if event.button != 3:
            return False
        path_info = self._tree.get_path_at_pos(int(event.x), int(event.y))
        if path_info is None:
            return False
        path = path_info[0]
        self._tree.get_selection().select_path(path)
        self._show_context_menu(event)
        return True

    # ── context menu ────────────────────────────────────────────────────

    def _show_context_menu(self, event: Gdk.EventButton) -> None:
        """Build and display the right-click context menu.

        The menu is stored in *self._context_menu* to prevent premature
        garbage collection (which causes segfaults with GTK menus).
        """
        model = self._tree.get_model()
        sel = self._tree.get_selection()
        _, tree_iter = sel.get_selected()
        if tree_iter is None:
            return

        is_folder: bool = model[tree_iter][COL_IS_FOLDER]
        menu = Gtk.Menu()

        if not is_folder:
            self._add_menu_item(menu, "Connect", self._ctx_connect)
            self._add_menu_item(menu, "Edit", self._ctx_edit)
            self._add_menu_item(menu, "Clone", self._ctx_clone)

        self._add_menu_item(menu, "Rename", self._ctx_rename)
        self._add_menu_item(menu, "Delete", self._ctx_delete)

        if not is_folder:
            menu.append(Gtk.SeparatorMenuItem())
            self._add_menu_item(menu, "Move to Folder", self._ctx_move_to_folder)
            self._add_menu_item(menu, "Export", self._ctx_export)

        menu.show_all()
        self._context_menu = menu  # prevent GC
        menu.popup(None, None, None, None, event.button, event.time)

    @staticmethod
    def _add_menu_item(
        menu: Gtk.Menu, label: str, callback: Any,
    ) -> Gtk.MenuItem:
        item = Gtk.MenuItem(label=label)
        item.connect("activate", callback)
        menu.append(item)
        return item

    # ── context-menu callbacks ──────────────────────────────────────────

    def _ctx_connect(self, _item: Gtk.MenuItem) -> None:
        session = self.get_selected_session()
        if session is not None:
            self.emit("session-activated", session)

    def _ctx_edit(self, _item: Gtk.MenuItem) -> None:
        """Open a dialog to edit the selected session."""
        session = self.get_selected_session()
        if session is None:
            return
        edited = self._run_session_dialog(session)
        if edited is not None:
            self._update_selected_row(edited)

    def _ctx_clone(self, _item: Gtk.MenuItem) -> None:
        """Duplicate the selected session under a new name."""
        session = self.get_selected_session()
        if session is None:
            return
        clone = SSHSession(**asdict(session))
        clone.session_name = f"{session.session_name} (copy)"
        self.add_session(clone)

    def _ctx_rename(self, _item: Gtk.MenuItem) -> None:
        """Prompt for a new name and apply it to the selected row."""
        sel = self._tree.get_selection()
        model, tree_iter = sel.get_selected()
        if tree_iter is None:
            return

        old_name: str = model[tree_iter][COL_NAME]
        dialog = Gtk.Dialog(
            title="Rename",
            transient_for=self.get_toplevel(),
            flags=0,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        entry = Gtk.Entry()
        entry.set_text(old_name)
        entry.connect("activate", lambda *_a: dialog.response(Gtk.ResponseType.OK))
        dialog.get_content_area().pack_start(entry, True, True, 8)
        dialog.show_all()

        if dialog.run() == Gtk.ResponseType.OK:
            new_name = entry.get_text().strip()
            if new_name:
                # Convert filter iter → child (store) iter.
                child_iter = self._filter_model.convert_iter_to_child_iter(tree_iter)
                self._store.set_value(child_iter, COL_NAME, new_name)
                # Update folder_iters mapping when renaming a folder.
                if model[tree_iter][COL_IS_FOLDER] and old_name in self._folder_iters:
                    self._folder_iters[new_name] = self._folder_iters.pop(old_name)
        dialog.destroy()

    def _ctx_delete(self, _item: Gtk.MenuItem) -> None:
        self._on_delete(None)

    def _ctx_move_to_folder(self, _item: Gtk.MenuItem) -> None:
        """Let the user pick a target folder, then move the session."""
        session = self.get_selected_session()
        if session is None:
            return

        folder_names = sorted(self._folder_iters.keys())
        if not folder_names:
            return

        dialog = Gtk.Dialog(
            title="Move to Folder",
            transient_for=self.get_toplevel(),
            flags=0,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        combo = Gtk.ComboBoxText()
        for name in folder_names:
            combo.append_text(name)
        combo.set_active(0)
        dialog.get_content_area().pack_start(combo, True, True, 8)
        dialog.show_all()

        if dialog.run() == Gtk.ResponseType.OK:
            target = combo.get_active_text()
            if target:
                self._delete_selected_row()
                session.folder = target
                self.add_session(session)
        dialog.destroy()

    def _ctx_export(self, _item: Gtk.MenuItem) -> None:
        """Export the selected session to a JSON file."""
        session = self.get_selected_session()
        if session is None:
            return

        dialog = Gtk.FileChooserDialog(
            title="Export Session",
            parent=self.get_toplevel(),
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE, Gtk.ResponseType.ACCEPT,
        )
        dialog.set_current_name(f"{session.session_name or 'session'}.json")
        json_filter = Gtk.FileFilter()
        json_filter.set_name("JSON files")
        json_filter.add_pattern("*.json")
        dialog.add_filter(json_filter)

        if dialog.run() == Gtk.ResponseType.ACCEPT:
            path = dialog.get_filename()
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(asdict(session), fh, indent=2)
            except OSError:
                logger.exception("Failed to export session to %s", path)
        dialog.destroy()

    # ── button callbacks ────────────────────────────────────────────────

    def _on_new_session(self, _btn: Optional[Gtk.Button]) -> None:
        """Open the session-edit dialog for a brand-new session."""
        session = SSHSession()
        edited = self._run_session_dialog(session)
        if edited is not None:
            self.add_session(edited)

    def _on_new_folder(self, _btn: Optional[Gtk.Button]) -> None:
        dialog = Gtk.Dialog(
            title="New Folder",
            transient_for=self.get_toplevel(),
            flags=0,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        entry = Gtk.Entry()
        entry.set_placeholder_text("Folder name")
        entry.connect("activate", lambda *_a: dialog.response(Gtk.ResponseType.OK))
        dialog.get_content_area().pack_start(entry, True, True, 8)
        dialog.show_all()

        if dialog.run() == Gtk.ResponseType.OK:
            name = entry.get_text().strip()
            if name:
                self.add_folder(name)
        dialog.destroy()

    def _on_delete(self, _btn: Optional[Gtk.Button]) -> None:
        """Delete the selected row after user confirmation."""
        sel = self._tree.get_selection()
        model, tree_iter = sel.get_selected()
        if tree_iter is None:
            return

        name: str = model[tree_iter][COL_NAME]
        kind = "folder" if model[tree_iter][COL_IS_FOLDER] else "session"

        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Delete {kind} \u201c{name}\u201d?",
        )
        dialog.format_secondary_text(
            "This cannot be undone." if kind == "session"
            else "All sessions inside the folder will also be removed.",
        )

        if dialog.run() == Gtk.ResponseType.YES:
            self._delete_selected_row()
        dialog.destroy()

    # ── row mutation helpers ────────────────────────────────────────────

    def _delete_selected_row(self) -> None:
        """Remove the currently selected row from the underlying store."""
        sel = self._tree.get_selection()
        model, tree_iter = sel.get_selected()
        if tree_iter is None:
            return
        # Remove from folder_iters if it was a folder.
        if model[tree_iter][COL_IS_FOLDER]:
            name = model[tree_iter][COL_NAME]
            self._folder_iters.pop(name, None)
        child_iter = self._filter_model.convert_iter_to_child_iter(tree_iter)
        self._store.remove(child_iter)

    def _update_selected_row(self, session: SSHSession) -> None:
        """Replace the data in the currently selected row with *session*."""
        sel = self._tree.get_selection()
        model, tree_iter = sel.get_selected()
        if tree_iter is None:
            return
        child_iter = self._filter_model.convert_iter_to_child_iter(tree_iter)
        icon_name = _PROTOCOL_ICONS.get(session.protocol, _DEFAULT_SESSION_ICON)
        icon = _resolve_icon(icon_name)
        data = json.dumps(asdict(session))
        display_name = session.session_name or session.hostname or "(unnamed)"
        self._store[child_iter] = [icon, display_name, data, False, session.protocol]

    # ── session-edit dialog ─────────────────────────────────────────────

    def _run_session_dialog(self, session: SSHSession) -> Optional[SSHSession]:
        """Show a dialog to edit core session fields.

        Parameters
        ----------
        session:
            Pre-populated session (may be empty for new sessions).

        Returns
        -------
        SSHSession or None
            The edited session, or *None* if the user cancelled.
        """
        dialog = Gtk.Dialog(
            title="Session Properties",
            transient_for=self.get_toplevel(),
            flags=0,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        dialog.set_default_size(380, -1)
        content = dialog.get_content_area()
        content.set_spacing(6)
        content.set_border_width(8)

        grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        fields: dict[str, Gtk.Entry | Gtk.ComboBoxText] = {}

        row = 0
        for label_text, attr, placeholder in (
            ("Name:", "session_name", "My Server"),
            ("Hostname:", "hostname", "192.168.1.1"),
            ("Port:", "port", "22"),
            ("Username:", "username", "root"),
            ("Folder:", "folder", "Default"),
        ):
            lbl = Gtk.Label(label=label_text, xalign=1.0)
            entry = Gtk.Entry()
            entry.set_placeholder_text(placeholder)
            entry.set_text(str(getattr(session, attr)))
            entry.set_hexpand(True)
            grid.attach(lbl, 0, row, 1, 1)
            grid.attach(entry, 1, row, 1, 1)
            fields[attr] = entry
            row += 1

        # Protocol combo.
        lbl = Gtk.Label(label="Protocol:", xalign=1.0)
        combo = Gtk.ComboBoxText()
        for proto in ("ssh2", "telnet", "serial", "raw", "rlogin"):
            combo.append_text(proto)
        combo.set_active_id(session.protocol)
        # Fallback: select by iterating entries.
        if combo.get_active() == -1:
            for idx, proto in enumerate(("ssh2", "telnet", "serial", "raw", "rlogin")):
                if proto == session.protocol:
                    combo.set_active(idx)
                    break
            else:
                combo.set_active(0)
        grid.attach(lbl, 0, row, 1, 1)
        grid.attach(combo, 1, row, 1, 1)
        fields["protocol"] = combo

        content.pack_start(grid, True, True, 0)
        dialog.show_all()

        result: Optional[SSHSession] = None
        if dialog.run() == Gtk.ResponseType.OK:
            result = SSHSession(**asdict(session))  # start from a copy
            result.session_name = fields["session_name"].get_text().strip()
            result.hostname = fields["hostname"].get_text().strip()
            result.username = fields["username"].get_text().strip()
            result.folder = fields["folder"].get_text().strip() or "Default"
            try:
                result.port = int(fields["port"].get_text().strip())
            except ValueError:
                result.port = 22
            result.protocol = combo.get_active_text() or "ssh2"
        dialog.destroy()
        return result
