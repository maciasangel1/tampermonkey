"""Session manager sidebar for FedoraXTerm.

Displays saved SSH sessions organised by folder in a TreeView and
provides quick-connect / edit / delete actions.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango

from fedoraxterm.settings import SettingsManager, SSHSession


class SessionSidebar(Gtk.Box):
    """Sidebar widget listing saved SSH sessions grouped by folder."""

    def __init__(self, settings_manager: SettingsManager, on_connect_callback=None):
        """
        Args:
            settings_manager: The application's :class:`SettingsManager`.
            on_connect_callback: Called with an :class:`SSHSession` when the
                user wants to open a session.
        """
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_size_request(100, -1)

        self._sm = settings_manager
        self._on_connect = on_connect_callback

        # -- Header --
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        header.set_margin_start(4)
        header.set_margin_end(4)
        header.set_margin_top(6)
        lbl = Gtk.Label(label="Sessions")
        lbl.set_xalign(0)
        lbl.get_style_context().add_class("title-4")
        header.pack_start(lbl, True, True, 0)

        add_btn = Gtk.Button.new_from_icon_name("list-add-symbolic", Gtk.IconSize.BUTTON)
        add_btn.set_tooltip_text("New SSH Session")
        add_btn.connect("clicked", self._on_add_clicked)
        header.pack_end(add_btn, False, False, 0)

        self.pack_start(header, False, False, 0)

        # -- TreeView (folder → sessions) --
        # Columns: icon-name, display-text, session-name (hidden key)
        self._store = Gtk.TreeStore(str, str, str)
        self._tree = Gtk.TreeView(model=self._store)
        self._tree.set_headers_visible(False)
        self._tree.set_activate_on_single_click(False)

        col = Gtk.TreeViewColumn()
        col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        icon_renderer = Gtk.CellRendererPixbuf()
        col.pack_start(icon_renderer, False)
        col.add_attribute(icon_renderer, "icon-name", 0)

        text_renderer = Gtk.CellRendererText()
        text_renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        text_renderer.set_property("xalign", 0.0)
        col.pack_start(text_renderer, True)
        col.add_attribute(text_renderer, "text", 1)
        self._tree.append_column(col)
        self._tree.set_fixed_height_mode(True)

        self._tree.connect("row-activated", self._on_row_activated)
        self._tree.connect("button-press-event", self._on_button_press)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self._tree)
        self.pack_start(scroll, True, True, 0)

        # -- Quick connect bar --
        qc_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        qc_box.set_margin_start(4)
        qc_box.set_margin_end(4)
        qc_box.set_margin_bottom(6)
        self._quick_entry = Gtk.Entry()
        self._quick_entry.set_placeholder_text("user@host")
        self._quick_entry.connect("activate", self._on_quick_connect)
        qc_box.pack_start(self._quick_entry, True, True, 0)
        qc_btn = Gtk.Button(label="Connect")
        qc_btn.connect("clicked", self._on_quick_connect)
        qc_box.pack_start(qc_btn, False, False, 0)
        self.pack_start(qc_box, False, False, 0)

        self.refresh()

    # -- Public API ---------------------------------------------------------

    def refresh(self):
        """Rebuild the tree from saved sessions."""
        self._store.clear()
        folders: dict[str, Gtk.TreeIter] = {}

        for session in self._sm.sessions:
            if session.folder not in folders:
                folders[session.folder] = self._store.append(
                    None, ["folder", session.folder, ""]
                )
            self._store.append(
                folders[session.folder],
                ["network-server-symbolic", session.display_label(), session.name],
            )

        self._tree.expand_all()

    # -- Internal helpers ---------------------------------------------------

    def _on_row_activated(self, _tree, path, _col):
        """Handle double-click on a row."""
        it = self._store.get_iter(path)
        session_name = self._store.get_value(it, 2)
        if not session_name:
            return  # folder row
        session = self._sm.get_session(session_name)
        if session and self._on_connect:
            self._on_connect(session)

    def _on_button_press(self, _tree, event):
        """Show context menu on right-click."""
        if event.button != 3:
            return False
        path_info = self._tree.get_path_at_pos(int(event.x), int(event.y))
        if not path_info:
            return False
        path = path_info[0]
        it = self._store.get_iter(path)
        session_name = self._store.get_value(it, 2)
        if not session_name:
            return False
        self._show_context_menu(event, session_name)
        return True

    def _show_context_menu(self, event, session_name: str):
        """Display a right-click context menu for a session."""
        menu = Gtk.Menu()

        connect_item = Gtk.MenuItem(label="Connect")
        connect_item.connect("activate", lambda _i: self._connect_session(session_name))
        menu.append(connect_item)

        edit_item = Gtk.MenuItem(label="Edit Credentials…")
        edit_item.connect("activate", lambda _i: self._edit_credentials(session_name))
        menu.append(edit_item)

        menu.append(Gtk.SeparatorMenuItem())

        delete_item = Gtk.MenuItem(label="Delete")
        delete_item.connect("activate", lambda _i: self._delete_session(session_name))
        menu.append(delete_item)

        menu.attach_to_widget(self._tree)
        menu.show_all()
        # Pass None instead of the Gdk.EventButton to avoid a segfault
        # caused by PyGObject event type conversion issues at the C level.
        menu.popup_at_pointer(None)

    def _connect_session(self, session_name: str):
        session = self._sm.get_session(session_name)
        if session and self._on_connect:
            self._on_connect(session)

    def _delete_session(self, session_name: str):
        self._sm.remove_session(session_name)
        self.refresh()

    def _edit_credentials(self, session_name: str):
        """Open a dialog to edit credentials for a saved session."""
        session = self._sm.get_session(session_name)
        if not session:
            return
        dialog = _CredentialsDialog(self.get_toplevel(), session)
        if dialog.run() == Gtk.ResponseType.OK:
            creds = dialog.get_credentials()
            self._sm.update_session(
                session_name,
                username=creds["username"],
                password=creds["password"],
                auth_method=creds["auth_method"],
                private_key_path=creds["private_key_path"],
            )
            self.refresh()
        dialog.destroy()

    def _on_add_clicked(self, _btn):
        """Open the new-session dialog."""
        dialog = _SSHSessionDialog(self.get_toplevel())
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            session = dialog.get_session()
            if session:
                self._sm.add_session(session)
                self.refresh()
        dialog.destroy()

    def _on_quick_connect(self, _widget):
        """Handle the quick-connect bar."""
        text = self._quick_entry.get_text().strip()
        if not text:
            return
        if "@" in text:
            user, host = text.split("@", 1)
        else:
            user, host = "", text
        session = SSHSession(name=f"quick-{host}", host=host, username=user)
        if self._on_connect:
            self._on_connect(session)
        self._quick_entry.set_text("")


# ---------------------------------------------------------------------------
# SSH Session Dialog
# ---------------------------------------------------------------------------


class _SSHSessionDialog(Gtk.Dialog):
    """Dialog for creating / editing an SSH session."""

    def __init__(self, parent=None, session: SSHSession | None = None):
        title = "Edit SSH Session" if session else "New SSH Session"
        super().__init__(
            title=title, transient_for=parent, modal=True
        )
        self.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("_OK", Gtk.ResponseType.OK)

        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        grid.set_margin_start(12)
        grid.set_margin_end(12)
        grid.set_margin_top(12)
        grid.set_margin_bottom(12)

        row = 0

        def add_field(label_text, entry_widget):
            nonlocal row
            lbl = Gtk.Label(label=label_text)
            lbl.set_xalign(1)
            grid.attach(lbl, 0, row, 1, 1)
            entry_widget.set_hexpand(True)
            grid.attach(entry_widget, 1, row, 1, 1)
            row += 1
            return entry_widget

        self._name_entry = add_field("Name:", Gtk.Entry())
        self._host_entry = add_field("Host:", Gtk.Entry())
        self._port_spin = add_field(
            "Port:",
            Gtk.SpinButton.new_with_range(1, 65535, 1),
        )
        self._port_spin.set_value(22)
        self._user_entry = add_field("Username:", Gtk.Entry())

        self._pass_entry = add_field("Password:", Gtk.Entry())
        self._pass_entry.set_visibility(False)
        self._pass_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)

        self._auth_combo = Gtk.ComboBoxText()
        self._auth_combo.append("password", "Password")
        self._auth_combo.append("key", "SSH Key")
        self._auth_combo.set_active_id("password")
        add_field("Auth:", self._auth_combo)

        self._key_chooser = Gtk.FileChooserButton(
            title="Select private key", action=Gtk.FileChooserAction.OPEN
        )
        add_field("Key File:", self._key_chooser)

        self._folder_entry = add_field("Folder:", Gtk.Entry())
        self._folder_entry.set_text("Default")

        # Pre-fill if editing
        if session:
            self._name_entry.set_text(session.name)
            self._host_entry.set_text(session.host)
            self._port_spin.set_value(session.port)
            self._user_entry.set_text(session.username)
            self._pass_entry.set_text(session.password)
            self._auth_combo.set_active_id(session.auth_method)
            self._folder_entry.set_text(session.folder)

        self.get_content_area().add(grid)
        self.show_all()

    def get_session(self) -> SSHSession | None:
        """Return an ``SSHSession`` from the dialog fields, or *None*."""
        name = self._name_entry.get_text().strip()
        host = self._host_entry.get_text().strip()
        if not name or not host:
            return None
        key_path = self._key_chooser.get_filename() or ""
        return SSHSession(
            name=name,
            host=host,
            port=int(self._port_spin.get_value()),
            username=self._user_entry.get_text().strip(),
            password=self._pass_entry.get_text(),
            auth_method=self._auth_combo.get_active_id() or "password",
            private_key_path=key_path,
            folder=self._folder_entry.get_text().strip() or "Default",
        )


# ---------------------------------------------------------------------------
# Credentials editing dialog
# ---------------------------------------------------------------------------


class _CredentialsDialog(Gtk.Dialog):
    """Dialog for editing credentials of an existing SSH session."""

    def __init__(self, parent, session: SSHSession):
        super().__init__(
            title=f"Edit Credentials — {session.name}",
            transient_for=parent,
            modal=True,
        )
        self.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("_Save", Gtk.ResponseType.OK)

        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        grid.set_margin_start(12)
        grid.set_margin_end(12)
        grid.set_margin_top(12)
        grid.set_margin_bottom(12)

        row = 0

        def add_field(label_text, widget):
            nonlocal row
            lbl = Gtk.Label(label=label_text)
            lbl.set_xalign(1)
            grid.attach(lbl, 0, row, 1, 1)
            widget.set_hexpand(True)
            grid.attach(widget, 1, row, 1, 1)
            row += 1
            return widget

        self._user_entry = add_field("Username:", Gtk.Entry())
        self._user_entry.set_text(session.username)

        self._pass_entry = add_field("Password:", Gtk.Entry())
        self._pass_entry.set_visibility(False)
        self._pass_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self._pass_entry.set_text(session.password)

        self._auth_combo = Gtk.ComboBoxText()
        self._auth_combo.append("password", "Password")
        self._auth_combo.append("key", "SSH Key")
        self._auth_combo.set_active_id(session.auth_method)
        add_field("Auth Method:", self._auth_combo)

        self._key_chooser = Gtk.FileChooserButton(
            title="Select private key", action=Gtk.FileChooserAction.OPEN
        )
        if session.private_key_path:
            self._key_chooser.set_filename(session.private_key_path)
        add_field("Key File:", self._key_chooser)

        self.get_content_area().add(grid)
        self.show_all()

    def get_credentials(self) -> dict:
        """Return a dict with the updated credential fields."""
        return {
            "username": self._user_entry.get_text().strip(),
            "password": self._pass_entry.get_text(),
            "auth_method": self._auth_combo.get_active_id() or "password",
            "private_key_path": self._key_chooser.get_filename() or "",
        }
