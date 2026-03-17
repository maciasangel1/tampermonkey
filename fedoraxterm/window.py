"""Main application window for FedoraXTerm.

Reproduces the MobaXterm layout:
* Left sidebar — session manager with saved SSH / RDP / VNC / serial sessions
* Centre — tabbed terminal area (VTE terminals for local / SSH / telnet / serial)
* Right sidebar (toggleable) — SFTP file browser (auto-opens with SSH sessions)
* Bottom bar — multi-execution input, status
* Menu bar & toolbar — access to all tools
"""

import os
from typing import Optional

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gtk, Gdk, GLib, Vte

from fedoraxterm import __app_name__, __version__
from fedoraxterm.settings import SettingsManager, SSHSession, AppSettings
from fedoraxterm.terminal import TerminalWidget
from fedoraxterm.sftp_browser import SFTPBrowser
from fedoraxterm.session_manager import SessionSidebar
from fedoraxterm.ssh_client import build_ssh_command, build_sftp_command
from fedoraxterm.network_tools import create_network_tools_dialog
from fedoraxterm.tunnel_manager import TunnelManager, create_tunnel_dialog
from fedoraxterm.multi_exec import MultiExecBar
from fedoraxterm.macro_manager import MacroManager, create_macro_dialog
from fedoraxterm.text_editor import TextEditorDialog
from fedoraxterm.remote_sessions import (
    RDPSession,
    VNCSession,
    SerialSession,
    build_telnet_command,
)


class MainWindow(Gtk.ApplicationWindow):
    """The primary FedoraXTerm window."""

    def __init__(self, application):
        super().__init__(
            application=application,
            title=__app_name__,
            default_width=1200,
            default_height=800,
        )

        # -- Managers --
        self._settings_mgr = SettingsManager()
        self._settings_mgr.load()
        self._tunnel_mgr = TunnelManager()
        self._macro_mgr = MacroManager()

        # Tab counter for unique tab names
        self._tab_counter = 0

        # -- Header bar --
        self._build_headerbar()

        # -- Main layout --
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(main_vbox)

        # Menubar
        main_vbox.pack_start(self._build_menubar(), False, False, 0)

        # Toolbar
        main_vbox.pack_start(self._build_toolbar(), False, False, 0)

        # Horizontal paned: sidebar | center + optional SFTP
        self._hpaned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        main_vbox.pack_start(self._hpaned, True, True, 0)

        # Left sidebar
        self._sidebar = SessionSidebar(
            self._settings_mgr, on_connect_callback=self._on_session_connect
        )
        sidebar_frame = Gtk.Frame()
        sidebar_frame.add(self._sidebar)
        self._hpaned.pack1(sidebar_frame, resize=False, shrink=False)
        self._hpaned.set_position(240)

        # Right area: terminal notebook + optional SFTP pane
        self._right_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self._hpaned.pack2(self._right_paned, resize=True, shrink=True)

        # Terminal notebook
        self._notebook = Gtk.Notebook()
        self._notebook.set_scrollable(True)
        self._notebook.popup_enable()
        self._notebook.connect("switch-page", self._on_tab_switched)
        self._right_paned.pack1(self._notebook, resize=True, shrink=True)

        # SFTP browser (right)
        self._sftp_browser = SFTPBrowser()
        sftp_frame = Gtk.Frame()
        sftp_frame.add(self._sftp_browser)
        self._right_paned.pack2(sftp_frame, resize=False, shrink=True)
        self._right_paned.set_position(800)

        # Multi-exec bar at the bottom
        self._multi_exec = MultiExecBar(
            get_terminals_callback=self._get_all_terminals
        )
        main_vbox.pack_start(self._multi_exec, False, False, 0)

        # Status bar
        self._statusbar = Gtk.Statusbar()
        main_vbox.pack_start(self._statusbar, False, False, 0)
        self._push_status("Ready")

        # Apply settings
        self._apply_window_settings()

        # Open an initial local terminal
        self.add_local_terminal_tab()

        self.show_all()

        # Honour show_sidebar setting
        if not self._settings_mgr.settings.show_sidebar:
            sidebar_frame.hide()

    # ======================================================================
    # Public API
    # ======================================================================

    def add_local_terminal_tab(self):
        """Open a new local shell terminal tab."""
        settings = self._settings_mgr.settings
        terminal = TerminalWidget(settings=settings)
        self._add_tab(terminal, "Local Shell")

    def add_ssh_terminal_tab(self, session: SSHSession):
        """Open a terminal tab connected via SSH."""
        cmd = build_ssh_command(
            host=session.host,
            port=session.port,
            username=session.username,
            auth_method=session.auth_method,
            private_key_path=session.private_key_path,
        )
        settings = self._settings_mgr.settings
        terminal = TerminalWidget(settings=settings, ssh_command=cmd)
        label = session.display_label()
        self._add_tab(terminal, label)

        # Auto-open SFTP browser for SSH sessions
        self._sftp_browser.disconnect()
        self._push_status(f"SSH → {session.host}")

    def show_ssh_dialog(self):
        """Open the New SSH Session dialog, then connect."""
        from fedoraxterm.session_manager import _SSHSessionDialog

        dialog = _SSHSessionDialog(self)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            session = dialog.get_session()
            if session:
                self._settings_mgr.add_session(session)
                self._sidebar.refresh()
                self.add_ssh_terminal_tab(session)
        dialog.destroy()

    def show_network_tools(self):
        """Open the Network Tools dialog."""
        dialog = create_network_tools_dialog(parent=self)
        dialog.show_all()

    # ======================================================================
    # UI building helpers
    # ======================================================================

    def _build_headerbar(self):
        hb = Gtk.HeaderBar()
        hb.set_show_close_button(True)
        hb.set_title(__app_name__)
        hb.set_subtitle("Enhanced Terminal & SSH Client for Linux")
        self.set_titlebar(hb)

        # Quick buttons on the headerbar
        new_term_btn = Gtk.Button.new_from_icon_name(
            "utilities-terminal-symbolic", Gtk.IconSize.BUTTON
        )
        new_term_btn.set_tooltip_text("New Local Terminal (Ctrl+T)")
        new_term_btn.connect("clicked", lambda _b: self.add_local_terminal_tab())
        hb.pack_start(new_term_btn)

        new_ssh_btn = Gtk.Button.new_from_icon_name(
            "network-server-symbolic", Gtk.IconSize.BUTTON
        )
        new_ssh_btn.set_tooltip_text("New SSH Session (Ctrl+N)")
        new_ssh_btn.connect("clicked", lambda _b: self.show_ssh_dialog())
        hb.pack_start(new_ssh_btn)

    def _build_menubar(self) -> Gtk.MenuBar:
        menubar = Gtk.MenuBar()

        # -- Sessions menu --
        sessions_menu = Gtk.Menu()
        sessions_item = Gtk.MenuItem(label="Sessions")
        sessions_item.set_submenu(sessions_menu)

        for label, cb in [
            ("New Local Shell", lambda _i: self.add_local_terminal_tab()),
            ("New SSH Session…", lambda _i: self.show_ssh_dialog()),
            ("New RDP Session…", lambda _i: self._show_rdp_dialog()),
            ("New VNC Session…", lambda _i: self._show_vnc_dialog()),
            ("New Telnet Session…", lambda _i: self._show_telnet_dialog()),
            ("New Serial Console…", lambda _i: self._show_serial_dialog()),
        ]:
            mi = Gtk.MenuItem(label=label)
            mi.connect("activate", cb)
            sessions_menu.append(mi)

        sessions_menu.append(Gtk.SeparatorMenuItem())
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda _i: self.get_application().quit())
        sessions_menu.append(quit_item)
        menubar.append(sessions_item)

        # -- Tools menu --
        tools_menu = Gtk.Menu()
        tools_item = Gtk.MenuItem(label="Tools")
        tools_item.set_submenu(tools_menu)

        for label, cb in [
            ("Network Tools…", lambda _i: self.show_network_tools()),
            ("SSH Tunnel Manager…", lambda _i: self._show_tunnel_dialog()),
            ("Macro Manager…", lambda _i: self._show_macro_dialog()),
            ("Text Editor…", lambda _i: self._show_text_editor()),
        ]:
            mi = Gtk.MenuItem(label=label)
            mi.connect("activate", cb)
            tools_menu.append(mi)
        menubar.append(tools_item)

        # -- View menu --
        view_menu = Gtk.Menu()
        view_item = Gtk.MenuItem(label="View")
        view_item.set_submenu(view_menu)

        toggle_sidebar = Gtk.CheckMenuItem(label="Show Sidebar")
        toggle_sidebar.set_active(self._settings_mgr.settings.show_sidebar)
        toggle_sidebar.connect("toggled", self._on_toggle_sidebar)
        view_menu.append(toggle_sidebar)

        toggle_multi = Gtk.CheckMenuItem(label="MultiExec Bar")
        toggle_multi.set_active(False)
        toggle_multi.connect("toggled", self._on_toggle_multi)
        view_menu.append(toggle_multi)
        menubar.append(view_item)

        # -- Macros menu --
        macro_menu = Gtk.Menu()
        macro_item = Gtk.MenuItem(label="Macros")
        macro_item.set_submenu(macro_menu)

        rec_item = Gtk.MenuItem(label="Start Recording")
        rec_item.connect("activate", self._on_start_recording)
        macro_menu.append(rec_item)
        self._rec_menu_item = rec_item

        stop_item = Gtk.MenuItem(label="Stop Recording")
        stop_item.connect("activate", self._on_stop_recording)
        stop_item.set_sensitive(False)
        macro_menu.append(stop_item)
        self._stop_rec_menu_item = stop_item

        menubar.append(macro_item)

        # -- Help menu --
        help_menu = Gtk.Menu()
        help_item = Gtk.MenuItem(label="Help")
        help_item.set_submenu(help_menu)

        about_item = Gtk.MenuItem(label="About")
        about_item.connect(
            "activate",
            lambda _i: self.get_application().activate_action("about", None),
        )
        help_menu.append(about_item)
        menubar.append(help_item)

        return menubar

    def _build_toolbar(self) -> Gtk.Toolbar:
        toolbar = Gtk.Toolbar()
        toolbar.set_style(Gtk.ToolbarStyle.BOTH_HORIZ)
        toolbar.set_icon_size(Gtk.IconSize.SMALL_TOOLBAR)

        items = [
            ("utilities-terminal", "Shell", self.add_local_terminal_tab),
            ("network-server", "SSH", self.show_ssh_dialog),
            ("preferences-desktop-remote-desktop", "RDP", self._show_rdp_dialog),
            ("preferences-desktop-display", "VNC", self._show_vnc_dialog),
            ("network-wired", "Telnet", self._show_telnet_dialog),
            ("media-removable", "Serial", self._show_serial_dialog),
            (None, None, None),  # separator
            ("network-workgroup", "Tunnels", self._show_tunnel_dialog),
            ("utilities-system-monitor", "Net Tools", self.show_network_tools),
            ("accessories-text-editor", "Editor", self._show_text_editor),
            ("media-record", "Macros", self._show_macro_dialog),
        ]
        for icon, label, callback in items:
            if icon is None:
                toolbar.insert(Gtk.SeparatorToolItem(), -1)
                continue
            btn = Gtk.ToolButton()
            btn.set_icon_name(icon)
            btn.set_label(label)
            btn.set_tooltip_text(label)
            btn.connect("clicked", lambda _b, cb=callback: cb())
            toolbar.insert(btn, -1)

        return toolbar

    # ======================================================================
    # Tab management
    # ======================================================================

    def _add_tab(self, terminal: TerminalWidget, title: str):
        """Add a new terminal tab with a close button."""
        self._tab_counter += 1

        # Tab label with close button
        tab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        label = Gtk.Label(label=title)
        label.set_max_width_chars(30)
        label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        tab_box.pack_start(label, True, True, 0)

        close_btn = Gtk.Button.new_from_icon_name(
            "window-close-symbolic", Gtk.IconSize.MENU
        )
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        close_btn.connect("clicked", self._on_close_tab, terminal)
        tab_box.pack_start(close_btn, False, False, 0)
        tab_box.show_all()

        idx = self._notebook.append_page(terminal, tab_box)
        self._notebook.set_tab_reorderable(terminal, True)
        terminal.show_all()
        self._notebook.set_current_page(idx)

    def _on_close_tab(self, _btn, terminal):
        idx = self._notebook.page_num(terminal)
        if idx >= 0:
            self._notebook.remove_page(idx)

    def _on_tab_switched(self, _notebook, page, _page_num):
        """Update the window title when tabs change."""
        if hasattr(page, "get_title"):
            self.set_title(f"{page.get_title()} — {__app_name__}")

    # ======================================================================
    # Session-type dialogs
    # ======================================================================

    def _on_session_connect(self, session: SSHSession):
        """Callback from the session sidebar."""
        self.add_ssh_terminal_tab(session)

    def _show_rdp_dialog(self):
        dialog = _SimpleSessionDialog(self, "RDP", fields=[
            ("Host", "host", ""),
            ("Port", "port", "3389"),
            ("Username", "username", ""),
            ("Domain", "domain", ""),
        ])
        if dialog.run() == Gtk.ResponseType.OK:
            vals = dialog.get_values()
            rdp = RDPSession(
                name=f"RDP-{vals['host']}",
                host=vals["host"],
                port=int(vals.get("port", "3389") or "3389"),
                username=vals.get("username", ""),
                domain=vals.get("domain", ""),
            )
            cmd = rdp.build_command()
            term = TerminalWidget(
                settings=self._settings_mgr.settings, ssh_command=cmd
            )
            self._add_tab(term, f"RDP: {vals['host']}")
        dialog.destroy()

    def _show_vnc_dialog(self):
        dialog = _SimpleSessionDialog(self, "VNC", fields=[
            ("Host", "host", ""),
            ("Port", "port", "5900"),
        ])
        if dialog.run() == Gtk.ResponseType.OK:
            vals = dialog.get_values()
            vnc = VNCSession(
                name=f"VNC-{vals['host']}",
                host=vals["host"],
                port=int(vals.get("port", "5900") or "5900"),
            )
            cmd = vnc.build_command()
            term = TerminalWidget(
                settings=self._settings_mgr.settings, ssh_command=cmd
            )
            self._add_tab(term, f"VNC: {vals['host']}")
        dialog.destroy()

    def _show_telnet_dialog(self):
        dialog = _SimpleSessionDialog(self, "Telnet", fields=[
            ("Host", "host", ""),
            ("Port", "port", "23"),
        ])
        if dialog.run() == Gtk.ResponseType.OK:
            vals = dialog.get_values()
            cmd = build_telnet_command(
                vals["host"], int(vals.get("port", "23") or "23")
            )
            term = TerminalWidget(
                settings=self._settings_mgr.settings, ssh_command=cmd
            )
            self._add_tab(term, f"Telnet: {vals['host']}")
        dialog.destroy()

    def _show_serial_dialog(self):
        dialog = _SimpleSessionDialog(self, "Serial Console", fields=[
            ("Device", "device", "/dev/ttyUSB0"),
            ("Baud Rate", "baud", "115200"),
        ])
        if dialog.run() == Gtk.ResponseType.OK:
            vals = dialog.get_values()
            serial = SerialSession(
                name=f"Serial-{vals['device']}",
                device=vals["device"],
                baud_rate=int(vals.get("baud", "115200") or "115200"),
            )
            cmd = serial.build_command()
            term = TerminalWidget(
                settings=self._settings_mgr.settings, ssh_command=cmd
            )
            self._add_tab(term, f"Serial: {vals['device']}")
        dialog.destroy()

    # ======================================================================
    # Tool dialogs
    # ======================================================================

    def _show_tunnel_dialog(self):
        dialog = create_tunnel_dialog(parent=self, manager=self._tunnel_mgr)
        dialog.show_all()

    def _show_macro_dialog(self):
        dialog = create_macro_dialog(
            parent=self,
            macro_manager=self._macro_mgr,
            play_callback=self._play_macro,
        )
        dialog.show_all()

    def _show_text_editor(self, filepath: Optional[str] = None):
        editor = TextEditorDialog(parent=self, filepath=filepath)
        editor.show_all()

    # ======================================================================
    # View toggles
    # ======================================================================

    def _on_toggle_sidebar(self, item):
        parent = self._hpaned.get_child1()
        if item.get_active():
            parent.show()
        else:
            parent.hide()
        self._settings_mgr.settings.show_sidebar = item.get_active()

    def _on_toggle_multi(self, item):
        if item.get_active():
            self._multi_exec.show()
            self._multi_exec.enabled = True
        else:
            self._multi_exec.hide()
            self._multi_exec.enabled = False

    # ======================================================================
    # Multi-exec helpers
    # ======================================================================

    def _get_all_terminals(self):
        """Return a list of ``(label, TerminalWidget)`` for all open tabs."""
        result = []
        for i in range(self._notebook.get_n_pages()):
            page = self._notebook.get_nth_page(i)
            if isinstance(page, TerminalWidget):
                tab_label = self._notebook.get_tab_label(page)
                text = ""
                if tab_label:
                    for child in tab_label.get_children():
                        if isinstance(child, Gtk.Label):
                            text = child.get_text()
                            break
                result.append((text, page))
        return result

    # ======================================================================
    # Macro helpers
    # ======================================================================

    def _on_start_recording(self, _item):
        dialog = Gtk.Dialog(
            title="Macro Name", transient_for=self, modal=True
        )
        dialog.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("_OK", Gtk.ResponseType.OK)
        entry = Gtk.Entry()
        entry.set_placeholder_text("Enter macro name…")
        dialog.get_content_area().pack_start(entry, True, True, 8)
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            name = entry.get_text().strip()
            if name:
                self._macro_mgr.start_recording(name)
                self._rec_menu_item.set_sensitive(False)
                self._stop_rec_menu_item.set_sensitive(True)
                self._push_status(f"Recording macro: {name}")
        dialog.destroy()

    def _on_stop_recording(self, _item):
        macro = self._macro_mgr.stop_recording()
        self._rec_menu_item.set_sensitive(True)
        self._stop_rec_menu_item.set_sensitive(False)
        if macro:
            self._push_status(
                f"Macro '{macro.name}' saved ({len(macro.commands)} commands)"
            )
        else:
            self._push_status("Recording stopped (no commands captured)")

    def _play_macro(self, name: str):
        """Play a macro into the current terminal tab."""
        idx = self._notebook.get_current_page()
        if idx < 0:
            return
        page = self._notebook.get_nth_page(idx)
        if isinstance(page, TerminalWidget):
            self._macro_mgr.play(name, page)

    # ======================================================================
    # Misc
    # ======================================================================

    def _apply_window_settings(self):
        s = self._settings_mgr.settings
        self.set_default_size(s.window_width, s.window_height)

    def _push_status(self, text: str):
        ctx = self._statusbar.get_context_id("main")
        self._statusbar.push(ctx, text)


# ======================================================================
# Generic simple-session dialog
# ======================================================================


class _SimpleSessionDialog(Gtk.Dialog):
    """A generic dialog with a dynamic set of labelled entries."""

    def __init__(self, parent, title: str, fields: list[tuple[str, str, str]]):
        """
        Args:
            parent: Parent window.
            title: Dialog title.
            fields: List of ``(display_label, key, default_value)`` tuples.
        """
        super().__init__(
            title=f"New {title} Session",
            transient_for=parent,
            modal=True,
        )
        self.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("_Connect", Gtk.ResponseType.OK)

        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        grid.set_margin_start(12)
        grid.set_margin_end(12)
        grid.set_margin_top(12)
        grid.set_margin_bottom(12)

        self._entries: dict[str, Gtk.Entry] = {}
        for row, (label_text, key, default) in enumerate(fields):
            lbl = Gtk.Label(label=label_text + ":")
            lbl.set_xalign(1)
            grid.attach(lbl, 0, row, 1, 1)
            entry = Gtk.Entry()
            entry.set_text(default)
            entry.set_hexpand(True)
            grid.attach(entry, 1, row, 1, 1)
            self._entries[key] = entry

        self.get_content_area().add(grid)
        self.show_all()

    def get_values(self) -> dict[str, str]:
        return {k: e.get_text().strip() for k, e in self._entries.items()}
