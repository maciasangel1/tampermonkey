"""Local file browser widget for FedoraXTerm.

Shows files and directories in the current working directory of the active
terminal.  Supports navigation, double-click to descend into directories,
drag-and-drop, and a right-click context menu for file management.
"""

import os
import shutil
import stat

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango


def _human_size(size_bytes: int) -> str:
    """Return a human-readable file size string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.0f} {unit}" if unit == "B" else f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


class LocalFileBrowser(Gtk.Box):
    """A file-browser panel that displays local filesystem contents."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        self._current_path = os.path.expanduser("~")
        self._on_open_file_callback = None
        self._on_drop_to_terminal_callback = None
        self._show_hidden = False

        # -- Header bar: path entry + buttons --------------------------------
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        header.set_margin_start(4)
        header.set_margin_end(4)
        header.set_margin_top(4)
        header.set_margin_bottom(2)

        # Close / hide button
        self._close_btn = Gtk.Button()
        self._close_btn.set_image(
            Gtk.Image.new_from_icon_name("window-close-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        )
        self._close_btn.set_tooltip_text("Hide file browser")
        self._close_btn.set_relief(Gtk.ReliefStyle.NONE)
        header.pack_start(self._close_btn, False, False, 0)

        # Label
        lbl = Gtk.Label(label="Files")
        lbl.set_xalign(0)
        lbl.get_style_context().add_class("dim-label")
        header.pack_start(lbl, False, False, 4)

        # Parent directory button
        up_btn = Gtk.Button()
        up_btn.set_image(
            Gtk.Image.new_from_icon_name("go-up-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        )
        up_btn.set_tooltip_text("Parent directory")
        up_btn.set_relief(Gtk.ReliefStyle.NONE)
        up_btn.connect("clicked", self._on_go_up)
        header.pack_start(up_btn, False, False, 0)

        # Refresh button
        ref_btn = Gtk.Button()
        ref_btn.set_image(
            Gtk.Image.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        )
        ref_btn.set_tooltip_text("Refresh")
        ref_btn.set_relief(Gtk.ReliefStyle.NONE)
        ref_btn.connect("clicked", lambda _b: self.refresh())
        header.pack_start(ref_btn, False, False, 0)

        # Home button
        home_btn = Gtk.Button()
        home_btn.set_image(
            Gtk.Image.new_from_icon_name("go-home-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        )
        home_btn.set_tooltip_text("Home directory")
        home_btn.set_relief(Gtk.ReliefStyle.NONE)
        home_btn.connect("clicked", self._on_go_home)
        header.pack_start(home_btn, False, False, 0)

        # Toggle hidden files
        self._hidden_btn = Gtk.ToggleButton()
        self._hidden_btn.set_image(
            Gtk.Image.new_from_icon_name("view-reveal-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        )
        self._hidden_btn.set_tooltip_text("Show hidden files")
        self._hidden_btn.set_relief(Gtk.ReliefStyle.NONE)
        self._hidden_btn.connect("toggled", self._on_toggle_hidden)
        header.pack_start(self._hidden_btn, False, False, 0)

        self.pack_start(header, False, False, 0)

        # -- Path entry -------------------------------------------------------
        self._path_entry = Gtk.Entry()
        self._path_entry.set_text(self._current_path)
        self._path_entry.set_margin_start(4)
        self._path_entry.set_margin_end(4)
        self._path_entry.connect("activate", self._on_path_activate)
        self.pack_start(self._path_entry, False, False, 0)

        # -- File list (TreeView) ---------------------------------------------
        # Columns: icon_name, display_name, size_str, is_dir, full_path
        self._store = Gtk.ListStore(str, str, str, bool, str)
        self._tree = Gtk.TreeView(model=self._store)
        self._tree.set_headers_visible(True)
        self._tree.set_enable_search(True)
        self._tree.set_search_column(1)

        # Icon + name column
        col_name = Gtk.TreeViewColumn("Name")
        col_name.set_expand(True)
        col_name.set_sort_column_id(1)

        icon_renderer = Gtk.CellRendererPixbuf()
        col_name.pack_start(icon_renderer, False)
        col_name.add_attribute(icon_renderer, "icon-name", 0)

        name_renderer = Gtk.CellRendererText()
        name_renderer.set_property("ellipsize", Pango.EllipsizeMode.MIDDLE)
        col_name.pack_start(name_renderer, True)
        col_name.add_attribute(name_renderer, "text", 1)
        self._tree.append_column(col_name)

        # Size column
        size_renderer = Gtk.CellRendererText()
        size_renderer.set_property("xalign", 1.0)
        col_size = Gtk.TreeViewColumn("Size", size_renderer, text=2)
        col_size.set_min_width(70)
        col_size.set_sort_column_id(2)
        self._tree.append_column(col_size)

        self._tree.connect("row-activated", self._on_row_activated)
        self._tree.connect("button-press-event", self._on_button_press)

        # -- Drag-and-drop: drag files out of the browser --------------------
        self._tree.enable_model_drag_source(
            Gdk.ModifierType.BUTTON1_MASK,
            [Gtk.TargetEntry.new("text/uri-list", 0, 0)],
            Gdk.DragAction.COPY,
        )
        self._tree.connect("drag-data-get", self._on_drag_data_get)

        # Accept file drops into the browser (copy/move)
        self._tree.enable_model_drag_dest(
            [Gtk.TargetEntry.new("text/uri-list", 0, 0)],
            Gdk.DragAction.COPY,
        )
        self._tree.connect("drag-data-received", self._on_drag_data_received)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self._tree)
        self.pack_start(scroll, True, True, 0)

        self._populate(self._current_path)

    # -- Public API ----------------------------------------------------------

    def navigate_to(self, path: str):
        """Navigate the browser to *path*."""
        path = os.path.expanduser(path)
        if os.path.isdir(path):
            self._current_path = path
            self._path_entry.set_text(path)
            self._populate(path)

    def refresh(self):
        """Reload the current directory."""
        self._populate(self._current_path)

    def get_current_path(self) -> str:
        """Return the directory currently shown."""
        return self._current_path

    def set_on_close(self, callback):
        """Register a callback for the close/hide button."""
        self._close_btn.connect("clicked", lambda _b: callback())

    def set_on_open_file(self, callback):
        """Register *callback(filepath)* for when a file is opened."""
        self._on_open_file_callback = callback

    def set_on_drop_to_terminal(self, callback):
        """Register *callback(filepath)* to paste a file path into the terminal."""
        self._on_drop_to_terminal_callback = callback

    # -- Internal helpers ----------------------------------------------------

    def _populate(self, path: str):
        """Fill the store with entries from *path*."""
        self._store.clear()
        try:
            entries = os.listdir(path)
        except PermissionError:
            self._store.append(
                ["dialog-error-symbolic", "(Permission denied)", "", False, ""]
            )
            return
        except OSError as exc:
            self._store.append(
                ["dialog-error-symbolic", f"({exc})", "", False, ""]
            )
            return

        dirs = []
        files = []
        for name in sorted(entries, key=str.lower):
            if not self._show_hidden and name.startswith("."):
                continue
            full = os.path.join(path, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            if stat.S_ISDIR(st.st_mode):
                dirs.append((name, full))
            else:
                files.append((name, full, st.st_size))

        for name, full in dirs:
            self._store.append(
                ["folder-symbolic", name, "", True, full]
            )
        for name, full, size in files:
            icon = self._icon_for_file(name)
            self._store.append(
                [icon, name, _human_size(size), False, full]
            )

    @staticmethod
    def _icon_for_file(name: str) -> str:
        """Choose a themed icon name based on file extension."""
        ext = os.path.splitext(name)[1].lower()
        mapping = {
            ".py": "text-x-python-symbolic",
            ".js": "text-x-script-symbolic",
            ".ts": "text-x-script-symbolic",
            ".sh": "text-x-script-symbolic",
            ".bash": "text-x-script-symbolic",
            ".json": "text-x-generic-symbolic",
            ".yaml": "text-x-generic-symbolic",
            ".yml": "text-x-generic-symbolic",
            ".xml": "text-x-generic-symbolic",
            ".html": "text-html-symbolic",
            ".css": "text-x-generic-symbolic",
            ".md": "text-x-generic-symbolic",
            ".txt": "text-x-generic-symbolic",
            ".log": "text-x-generic-symbolic",
            ".cfg": "text-x-generic-symbolic",
            ".ini": "text-x-generic-symbolic",
            ".conf": "text-x-generic-symbolic",
            ".c": "text-x-csrc-symbolic",
            ".cpp": "text-x-csrc-symbolic",
            ".h": "text-x-chdr-symbolic",
            ".rs": "text-x-script-symbolic",
            ".go": "text-x-script-symbolic",
            ".java": "text-x-java-symbolic",
            ".png": "image-x-generic-symbolic",
            ".jpg": "image-x-generic-symbolic",
            ".jpeg": "image-x-generic-symbolic",
            ".gif": "image-x-generic-symbolic",
            ".svg": "image-x-generic-symbolic",
            ".zip": "package-x-generic-symbolic",
            ".tar": "package-x-generic-symbolic",
            ".gz": "package-x-generic-symbolic",
            ".rpm": "package-x-generic-symbolic",
            ".deb": "package-x-generic-symbolic",
        }
        return mapping.get(ext, "text-x-generic-symbolic")

    # -- Signal handlers -----------------------------------------------------

    def _on_row_activated(self, _tree, path, _column):
        """Handle double-click on a row."""
        row = self._store[path]
        is_dir = row[3]
        full_path = row[4]
        if not full_path:
            return
        if is_dir:
            self.navigate_to(full_path)
        elif self._on_open_file_callback:
            self._on_open_file_callback(full_path)

    def _on_button_press(self, widget, event):
        """Handle right-click for context menu."""
        if event.button != 3:
            return False
        path_info = self._tree.get_path_at_pos(int(event.x), int(event.y))
        if path_info is None:
            # Right-click on empty area
            self._show_empty_context_menu(event)
            return True
        tree_path = path_info[0]
        self._tree.get_selection().select_path(tree_path)
        row = self._store[tree_path]
        full_path = row[4]
        is_dir = row[3]
        if not full_path:
            return False
        self._show_item_context_menu(event, full_path, is_dir)
        return True

    def _show_item_context_menu(self, event, full_path, is_dir):
        """Show context menu for a file or directory."""
        menu = Gtk.Menu()

        if is_dir:
            open_item = Gtk.MenuItem(label="Open")
            open_item.connect("activate", lambda _i: self.navigate_to(full_path))
            menu.append(open_item)

            open_term = Gtk.MenuItem(label="Open Terminal Here")
            open_term.connect(
                "activate",
                lambda _i: self._paste_path_to_terminal(f"cd {_shell_quote(full_path)}"),
            )
            menu.append(open_term)
        else:
            if self._on_open_file_callback:
                open_item = Gtk.MenuItem(label="Open in Editor")
                open_item.connect(
                    "activate", lambda _i: self._on_open_file_callback(full_path)
                )
                menu.append(open_item)

        menu.append(Gtk.SeparatorMenuItem())

        # Copy path
        copy_path = Gtk.MenuItem(label="Copy Path")
        copy_path.connect("activate", lambda _i: self._copy_to_clipboard(full_path))
        menu.append(copy_path)

        # Paste path to terminal
        paste_path = Gtk.MenuItem(label="Paste Path to Terminal")
        paste_path.connect(
            "activate",
            lambda _i: self._paste_path_to_terminal(_shell_quote(full_path)),
        )
        menu.append(paste_path)

        menu.append(Gtk.SeparatorMenuItem())

        # Rename
        rename_item = Gtk.MenuItem(label="Rename…")
        rename_item.connect("activate", lambda _i: self._rename_item(full_path))
        menu.append(rename_item)

        # Delete
        delete_item = Gtk.MenuItem(label="Delete")
        delete_item.connect("activate", lambda _i: self._delete_item(full_path))
        menu.append(delete_item)

        menu.show_all()
        self._file_context_menu = menu
        menu.attach_to_widget(self._tree, None)
        menu.popup(None, None, None, None, event.button, event.time)

    def _show_empty_context_menu(self, event):
        """Show context menu when right-clicking empty area."""
        menu = Gtk.Menu()

        new_folder = Gtk.MenuItem(label="New Folder…")
        new_folder.connect("activate", lambda _i: self._create_new_folder())
        menu.append(new_folder)

        new_file = Gtk.MenuItem(label="New File…")
        new_file.connect("activate", lambda _i: self._create_new_file())
        menu.append(new_file)

        menu.append(Gtk.SeparatorMenuItem())

        open_term = Gtk.MenuItem(label="Open Terminal Here")
        open_term.connect(
            "activate",
            lambda _i: self._paste_path_to_terminal(
                f"cd {_shell_quote(self._current_path)}"
            ),
        )
        menu.append(open_term)

        menu.show_all()
        self._file_context_menu = menu
        menu.attach_to_widget(self._tree, None)
        menu.popup(None, None, None, None, event.button, event.time)

    def _on_go_up(self, _btn):
        parent = os.path.dirname(self._current_path)
        if parent and parent != self._current_path:
            self.navigate_to(parent)

    def _on_go_home(self, _btn):
        self.navigate_to(os.path.expanduser("~"))

    def _on_path_activate(self, entry):
        """Navigate when the user presses Enter in the path entry."""
        text = entry.get_text().strip()
        if text:
            self.navigate_to(text)

    def _on_toggle_hidden(self, btn):
        """Toggle showing hidden files."""
        self._show_hidden = btn.get_active()
        self.refresh()

    # -- Drag-and-drop -------------------------------------------------------

    def _on_drag_data_get(self, _widget, _context, selection, _info, _time):
        """Provide file URIs when dragging out of the browser."""
        sel = self._tree.get_selection()
        model, tree_iter = sel.get_selected()
        if tree_iter is None:
            return
        full_path = model[tree_iter][4]
        if full_path:
            uri = GLib.filename_to_uri(full_path, None)
            selection.set_uris([uri])

    def _on_drag_data_received(
        self, _widget, _context, _x, _y, selection, _info, _time
    ):
        """Handle files dropped into the browser — copy them here."""
        uris = selection.get_uris()
        if not uris:
            return
        for uri in uris:
            src = GLib.filename_from_uri(uri)[0]
            if not src or not os.path.exists(src):
                continue
            dest = os.path.join(self._current_path, os.path.basename(src))
            try:
                if os.path.isdir(src):
                    shutil.copytree(src, dest)
                else:
                    shutil.copy2(src, dest)
            except OSError:
                pass
        self.refresh()

    # -- File management helpers ---------------------------------------------

    def _copy_to_clipboard(self, text):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)

    def _paste_path_to_terminal(self, text):
        if self._on_drop_to_terminal_callback:
            self._on_drop_to_terminal_callback(text)

    def _rename_item(self, full_path):
        """Show a dialog to rename a file or directory."""
        old_name = os.path.basename(full_path)
        dialog = Gtk.Dialog(
            title="Rename",
            transient_for=self.get_toplevel(),
            modal=True,
            destroy_with_parent=True,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        entry = Gtk.Entry()
        entry.set_text(old_name)
        entry.set_activates_default(True)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.get_content_area().pack_start(entry, True, True, 8)
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            new_name = entry.get_text().strip()
            if new_name and new_name != old_name:
                new_path = os.path.join(os.path.dirname(full_path), new_name)
                try:
                    os.rename(full_path, new_path)
                except OSError:
                    pass
                self.refresh()
        dialog.destroy()

    def _delete_item(self, full_path):
        """Delete a file or directory after confirmation."""
        name = os.path.basename(full_path)
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f'Delete "{name}"?',
        )
        dialog.format_secondary_text("This action cannot be undone.")
        if dialog.run() == Gtk.ResponseType.YES:
            try:
                if os.path.isdir(full_path):
                    shutil.rmtree(full_path)
                else:
                    os.remove(full_path)
            except OSError:
                pass
            self.refresh()
        dialog.destroy()

    def _create_new_folder(self):
        """Create a new directory in the current path."""
        dialog = Gtk.Dialog(
            title="New Folder",
            transient_for=self.get_toplevel(),
            modal=True,
            destroy_with_parent=True,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        entry = Gtk.Entry()
        entry.set_placeholder_text("Folder name")
        entry.set_activates_default(True)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.get_content_area().pack_start(entry, True, True, 8)
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            name = entry.get_text().strip()
            if name:
                try:
                    os.makedirs(os.path.join(self._current_path, name), exist_ok=True)
                except OSError:
                    pass
                self.refresh()
        dialog.destroy()

    def _create_new_file(self):
        """Create a new empty file in the current path."""
        dialog = Gtk.Dialog(
            title="New File",
            transient_for=self.get_toplevel(),
            modal=True,
            destroy_with_parent=True,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        entry = Gtk.Entry()
        entry.set_placeholder_text("File name")
        entry.set_activates_default(True)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.get_content_area().pack_start(entry, True, True, 8)
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            name = entry.get_text().strip()
            if name:
                fpath = os.path.join(self._current_path, name)
                try:
                    open(fpath, "a").close()
                except OSError:
                    pass
                self.refresh()
        dialog.destroy()


def _shell_quote(path: str) -> str:
    """Quote a path for safe use in a shell command."""
    import shlex
    return shlex.quote(path)
