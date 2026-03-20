"""Main application window for FedoraXTerm.

Reproduces the MobaXterm layout with a modern, macOS-inspired aesthetic:
* Left sidebar — session manager with saved SSH / RDP / VNC / serial sessions
* Centre — tabbed terminal area (VTE terminals for local / SSH / telnet / serial)
* Right sidebar (toggleable) — SFTP file browser (auto-opens with SSH sessions)
* Bottom bar — multi-execution input, status
* Header bar & toolbar — access to all tools
"""

import os
from typing import Optional

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gtk, Gdk, GLib, Pango, Vte

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


# ======================================================================
# macOS-inspired CSS theme
# ======================================================================

_MACOS_CSS = """
/* ---------- Global dark theme ---------- */
window, .background {
    background-color: #1c1c1e;
    color: #f5f5f7;
}

/* ---------- Header bar (title bar) ---------- */
headerbar {
    background: linear-gradient(to bottom, #3a3a3c, #2c2c2e);
    border-bottom: 1px solid #1c1c1e;
    padding: 2px 6px;
    min-height: 28px;
}
headerbar .title {
    font-weight: 600;
    font-size: 12px;
    color: #f5f5f7;
}
headerbar .subtitle {
    font-size: 10px;
    color: #98989d;
}
headerbar button {
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 2px 4px;
    color: #f5f5f7;
    min-height: 20px;
    min-width: 20px;
}
headerbar button:hover {
    background-color: rgba(255, 255, 255, 0.1);
}
headerbar button:active {
    background-color: rgba(255, 255, 255, 0.15);
}

/* ---------- Menu bar ---------- */
menubar {
    background-color: #2c2c2e;
    border-bottom: 1px solid #3a3a3c;
    padding: 1px 4px;
    color: #f5f5f7;
}
menubar > menuitem {
    padding: 2px 8px;
    border-radius: 4px;
    color: #f5f5f7;
}
menubar > menuitem:hover {
    background-color: #0a84ff;
}
menu {
    background-color: #2c2c2e;
    border: 1px solid #48484a;
    border-radius: 10px;
    padding: 4px 0;
}
menu menuitem {
    padding: 6px 16px;
    color: #f5f5f7;
}
menu menuitem:hover {
    background-color: #0a84ff;
    border-radius: 6px;
}
menu separator {
    background-color: #48484a;
    margin: 4px 12px;
    min-height: 1px;
}

/* ---------- Toolbar ---------- */
toolbar {
    background-color: #2c2c2e;
    border-bottom: 1px solid #3a3a3c;
    padding: 1px 4px;
}
toolbar .toolbar-button {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 2px 4px;
    color: #e5e5ea;
    margin: 0px 1px;
}
toolbar .toolbar-button:hover {
    background-color: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.12);
}
toolbar .toolbar-button:active {
    background-color: rgba(10, 132, 255, 0.25);
    border-color: #0a84ff;
}
toolbar .toolbar-button image {
    color: #0a84ff;
}
toolbar .toolbar-button label {
    color: #e5e5ea;
    font-size: 10px;
}
toolbar separator {
    background-color: #48484a;
    margin: 2px 2px;
    min-width: 1px;
}

/* ---------- Notebook tabs (top-positioned, horizontal) ---------- */
notebook {
    background-color: #1c1c1e;
}
notebook header {
    background-color: #2c2c2e;
    border-bottom: 1px solid #3a3a3c;
    padding: 0 4px;
}
notebook header tabs {
    background: transparent;
}
notebook header tab {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px 6px 0 0;
    padding: 4px 8px;
    margin: 1px 1px 0 1px;
    color: #98989d;
    min-height: 20px;
    min-width: 24px;
}
notebook header tab:checked {
    background-color: #1c1c1e;
    border-color: #3a3a3c;
    border-bottom-color: #0a84ff;
    color: #f5f5f7;
}
notebook header tab:hover:not(:checked) {
    background-color: rgba(255, 255, 255, 0.05);
    color: #e5e5ea;
}
notebook header tab label {
    font-size: 11px;
    padding: 0 2px;
}
notebook header tab button {
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 0px;
    min-height: 14px;
    min-width: 14px;
    color: #98989d;
}
notebook header tab button:hover {
    background-color: rgba(255, 255, 255, 0.12);
    color: #ff453a;
}

/* ---------- Sidebar ---------- */
.sidebar-frame {
    background-color: #1c1c1e;
    border-right: 1px solid #3a3a3c;
}
.sidebar-frame treeview {
    background-color: #1c1c1e;
    color: #f5f5f7;
}
.sidebar-frame treeview:selected {
    background-color: #0a84ff;
    color: white;
}
.sidebar-frame treeview:hover {
    background-color: rgba(255, 255, 255, 0.05);
}

/* ---------- SFTP pane ---------- */
.sftp-frame {
    background-color: #1c1c1e;
    border-top: 1px solid #3a3a3c;
}

/* ---------- Status bar ---------- */
.modern-statusbar {
    background-color: #2c2c2e;
    border-top: 1px solid #3a3a3c;
    padding: 3px 12px;
    color: #98989d;
    font-size: 11px;
    min-height: 22px;
}
.modern-statusbar label {
    color: #98989d;
    font-size: 11px;
}

/* ---------- Buttons (generic) ---------- */
button {
    border-radius: 6px;
    padding: 4px 12px;
    border: 1px solid #48484a;
    background: linear-gradient(to bottom, #3a3a3c, #2c2c2e);
    color: #f5f5f7;
    min-height: 24px;
}
button:hover {
    background: linear-gradient(to bottom, #48484a, #3a3a3c);
    border-color: #636366;
}
button:active {
    background-color: #0a84ff;
    border-color: #0a84ff;
}
button.flat, button.titlebutton {
    background: transparent;
    border: none;
}

/* ---------- Accent button ---------- */
.suggested-action {
    background: linear-gradient(to bottom, #0a84ff, #0070e0);
    border-color: #0060c0;
    color: white;
    font-weight: 600;
}
.suggested-action:hover {
    background: linear-gradient(to bottom, #409cff, #0a84ff);
}

/* ---------- Entries ---------- */
entry {
    background-color: #1c1c1e;
    color: #f5f5f7;
    border: 1px solid #48484a;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 26px;
}
entry:focus {
    border-color: #0a84ff;
}

/* ---------- Dialogs ---------- */
dialog .dialog-vbox {
    background-color: #2c2c2e;
}

/* ---------- Frames & Panes ---------- */
paned separator {
    background-color: #3a3a3c;
    min-width: 1px;
    min-height: 1px;
}
frame {
    border: none;
}

/* ---------- Scrollbar (thin, macOS style) ---------- */
scrollbar {
    background: transparent;
}
scrollbar slider {
    background-color: rgba(255, 255, 255, 0.2);
    border-radius: 4px;
    min-width: 6px;
    min-height: 6px;
}
scrollbar slider:hover {
    background-color: rgba(255, 255, 255, 0.35);
}
scrollbar slider:active {
    background-color: rgba(255, 255, 255, 0.5);
}

/* ---------- Tooltips ---------- */
tooltip {
    background-color: #2c2c2e;
    border: 1px solid #48484a;
    border-radius: 8px;
    color: #f5f5f7;
    padding: 6px 10px;
}

/* ---------- CheckButton ---------- */
checkbutton check {
    border-radius: 4px;
    border: 1px solid #636366;
    background-color: #1c1c1e;
    min-width: 16px;
    min-height: 16px;
}
checkbutton check:checked {
    background-color: #0a84ff;
    border-color: #0a84ff;
}

/* ---------- Spinner / Progress ---------- */
spinbutton {
    background-color: #1c1c1e;
    color: #f5f5f7;
    border: 1px solid #48484a;
    border-radius: 6px;
}
"""


# Tab label width constraints (in characters)
_TAB_LABEL_MIN_CHARS = 8   # Compact tabs — tooltip shows full title
_TAB_LABEL_MAX_CHARS = 20  # Maximum before ellipsis kicks in


def _load_css():
    """Load the macOS-inspired CSS theme into the default screen."""
    try:
        provider = Gtk.CssProvider()
        provider.load_from_data(_MACOS_CSS.encode("utf-8"))
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
    except Exception:
        # CSS loading is non-critical — fall back to default GTK theme
        pass


class MainWindow(Gtk.ApplicationWindow):
    """The primary FedoraXTerm window."""

    def __init__(self, application):
        super().__init__(
            application=application,
            title=__app_name__,
            default_width=1200,
            default_height=800,
        )

        # Load macOS-inspired theme
        _load_css()

        # -- Managers --
        self._settings_mgr = SettingsManager()
        self._settings_mgr.load()
        self._tunnel_mgr = TunnelManager()
        self._macro_mgr = MacroManager()

        # Tab counter for unique tab names
        self._tab_counter = 0
        self._focus_mode = False

        # -- Header bar --
        self._build_headerbar()

        # -- Main layout --
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(main_vbox)

        # Menubar
        self._menubar = self._build_menubar()
        main_vbox.pack_start(self._menubar, False, False, 0)

        # Toolbar
        self._toolbar = self._build_toolbar()
        main_vbox.pack_start(self._toolbar, False, False, 0)

        # Horizontal paned: left sidebar+SFTP | center terminal
        self._hpaned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        main_vbox.pack_start(self._hpaned, True, True, 0)

        # Left column: sessions sidebar on top, SFTP browser below
        self._left_vpaned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self._sidebar_frame = Gtk.Frame()
        self._sidebar_frame.get_style_context().add_class("sidebar-frame")

        self._sidebar = SessionSidebar(
            self._settings_mgr, on_connect_callback=self._on_session_connect
        )
        self._sidebar_frame.add(self._sidebar)
        self._left_vpaned.pack1(self._sidebar_frame, resize=True, shrink=False)

        # SFTP browser (below sessions, hidden by default)
        self._sftp_browser = SFTPBrowser()
        self._sftp_frame = Gtk.Frame()
        self._sftp_frame.get_style_context().add_class("sftp-frame")
        self._sftp_frame.add(self._sftp_browser)
        self._left_vpaned.pack2(self._sftp_frame, resize=True, shrink=True)
        self._sftp_visible = False

        self._hpaned.pack1(self._left_vpaned, resize=True, shrink=True)
        self._hpaned.set_position(260)

        # Terminal notebook (right / centre area)
        self._notebook = Gtk.Notebook()
        self._notebook.set_scrollable(True)
        # NOTE: Do NOT call popup_enable() — it enables GTK's built-in
        # right-click popup on tab labels which conflicts with our custom
        # _on_tab_right_click context menu and causes a segfault.
        self._notebook.connect("switch-page", self._on_tab_switched)
        pos_map = {
            "left": Gtk.PositionType.LEFT,
            "top": Gtk.PositionType.TOP,
            "bottom": Gtk.PositionType.BOTTOM,
            "right": Gtk.PositionType.RIGHT,
        }
        self._notebook.set_tab_pos(
            pos_map.get(self._settings_mgr.settings.tab_position, Gtk.PositionType.TOP)
        )
        self._hpaned.pack2(self._notebook, resize=True, shrink=False)

        # Multi-exec bar at the bottom
        self._multi_exec = MultiExecBar(
            get_terminals_callback=self._get_all_terminals
        )
        main_vbox.pack_start(self._multi_exec, False, False, 0)

        # Status bar (modern flat style)
        self._statusbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._statusbar.get_style_context().add_class("modern-statusbar")
        self._status_icon = Gtk.Image.new_from_icon_name(
            "emblem-default-symbolic", Gtk.IconSize.MENU
        )
        self._statusbar.pack_start(self._status_icon, False, False, 4)
        self._status_label = Gtk.Label(label="Ready")
        self._status_label.set_xalign(0)
        self._statusbar.pack_start(self._status_label, True, True, 0)
        self._tab_count_label = Gtk.Label()
        self._tab_count_label.set_xalign(1)
        self._statusbar.pack_end(self._tab_count_label, False, False, 8)
        main_vbox.pack_start(self._statusbar, False, False, 0)
        self._push_status("Ready")

        # Apply settings
        self._apply_window_settings()

        # Keyboard shortcut: F11 = toggle focus mode
        self.connect("key-press-event", self._on_key_press)

        # Open an initial local terminal
        self.add_local_terminal_tab()

        self.show_all()

        # Hide SFTP pane by default — opened automatically on SSH connect
        self._sftp_frame.hide()

        # Honour show_sidebar setting
        if not self._settings_mgr.settings.show_sidebar:
            self._sidebar_frame.hide()

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

        # Auto-enter saved password when the SSH prompt appears
        if session.auth_method == "password" and session.password:
            self._auto_enter_password(terminal, session.password)

        # Auto-open SFTP browser for SSH sessions
        self._sftp_browser.disconnect()
        self._sftp_browser.connect_sftp(
            host=session.host,
            port=session.port,
            username=session.username,
            password=session.password,
            private_key_path=session.private_key_path,
        )
        self._show_sftp_pane()
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
        hb.set_subtitle("Terminal & SSH Client")
        hb.set_decoration_layout("close,minimize,maximize:")
        self.set_titlebar(hb)

        # Left side: New terminal + New SSH (pill-shaped group)
        left_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)

        new_term_btn = Gtk.Button()
        term_icon = Gtk.Image.new_from_icon_name(
            "utilities-terminal-symbolic", Gtk.IconSize.BUTTON
        )
        new_term_btn.set_image(term_icon)
        new_term_btn.set_tooltip_text("New Local Terminal (Ctrl+T)")
        new_term_btn.set_relief(Gtk.ReliefStyle.NONE)
        new_term_btn.connect("clicked", lambda _b: self.add_local_terminal_tab())
        left_box.pack_start(new_term_btn, False, False, 0)

        new_ssh_btn = Gtk.Button()
        ssh_icon = Gtk.Image.new_from_icon_name(
            "network-server-symbolic", Gtk.IconSize.BUTTON
        )
        new_ssh_btn.set_image(ssh_icon)
        new_ssh_btn.set_tooltip_text("New SSH Session (Ctrl+N)")
        new_ssh_btn.set_relief(Gtk.ReliefStyle.NONE)
        new_ssh_btn.connect("clicked", lambda _b: self.show_ssh_dialog())
        left_box.pack_start(new_ssh_btn, False, False, 0)

        hb.pack_start(left_box)

        # Right side: settings gear
        settings_btn = Gtk.Button()
        gear_icon = Gtk.Image.new_from_icon_name(
            "emblem-system-symbolic", Gtk.IconSize.BUTTON
        )
        settings_btn.set_image(gear_icon)
        settings_btn.set_tooltip_text("Settings")
        settings_btn.set_relief(Gtk.ReliefStyle.NONE)
        settings_btn.connect("clicked", lambda _b: self._show_settings_dialog())
        hb.pack_end(settings_btn)

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
            ("Settings…", lambda _i: self._show_settings_dialog()),
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

        self._toggle_toolbar = Gtk.CheckMenuItem(label="Show Toolbar")
        self._toggle_toolbar.set_active(True)
        self._toggle_toolbar.connect("toggled", self._on_toggle_toolbar)
        view_menu.append(self._toggle_toolbar)

        toggle_multi = Gtk.CheckMenuItem(label="MultiExec Bar")
        toggle_multi.set_active(False)
        toggle_multi.connect("toggled", self._on_toggle_multi)
        view_menu.append(toggle_multi)

        self._toggle_sftp = Gtk.CheckMenuItem(label="SFTP File Browser")
        self._toggle_sftp.set_active(False)
        self._toggle_sftp.connect("toggled", self._on_toggle_sftp)
        view_menu.append(self._toggle_sftp)

        view_menu.append(Gtk.SeparatorMenuItem())

        self._focus_mode_item = Gtk.CheckMenuItem(label="Focus Mode (F11)")
        self._focus_mode_item.set_active(False)
        self._focus_mode_item.connect("toggled", self._on_toggle_focus_mode)
        view_menu.append(self._focus_mode_item)

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

    def _build_toolbar(self) -> Gtk.Box:
        toolbar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)
        toolbar_box.get_style_context().add_class("toolbar")
        toolbar_box.set_margin_start(4)
        toolbar_box.set_margin_end(4)
        toolbar_box.set_margin_top(1)
        toolbar_box.set_margin_bottom(1)

        items = [
            ("utilities-terminal-symbolic", "Shell", self.add_local_terminal_tab),
            ("network-server-symbolic", "SSH", self.show_ssh_dialog),
            ("preferences-desktop-remote-desktop-symbolic", "RDP", self._show_rdp_dialog),
            ("preferences-desktop-display-symbolic", "VNC", self._show_vnc_dialog),
            ("network-wired-symbolic", "Telnet", self._show_telnet_dialog),
            ("media-removable-symbolic", "Serial", self._show_serial_dialog),
            (None, None, None),  # separator
            ("network-workgroup-symbolic", "Tunnels", self._show_tunnel_dialog),
            ("utilities-system-monitor-symbolic", "Net Tools", self.show_network_tools),
            ("accessories-text-editor-symbolic", "Editor", self._show_text_editor),
            ("media-record-symbolic", "Macros", self._show_macro_dialog),
        ]
        for icon_name, label_text, callback in items:
            if icon_name is None:
                sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
                sep.set_margin_top(2)
                sep.set_margin_bottom(2)
                toolbar_box.pack_start(sep, False, False, 2)
                continue

            btn = Gtk.Button()
            btn.get_style_context().add_class("toolbar-button")
            btn.set_relief(Gtk.ReliefStyle.NONE)

            icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
            btn.set_image(icon)

            btn.set_tooltip_text(label_text)
            btn.connect("clicked", lambda _b, cb=callback: cb())
            toolbar_box.pack_start(btn, False, False, 0)

        return toolbar_box

    # ======================================================================
    # Tab management
    # ======================================================================

    def _add_tab(self, terminal: TerminalWidget, title: str):
        """Add a new terminal tab with a close button."""
        self._tab_counter += 1

        # Tab label with close button — horizontal layout for top-side tabs
        tab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        # Connection-type icon
        if title.startswith("SSH") or "@" in title:
            icon_name = "network-server-symbolic"
        elif title.startswith("RDP"):
            icon_name = "preferences-desktop-remote-desktop-symbolic"
        elif title.startswith("VNC"):
            icon_name = "preferences-desktop-display-symbolic"
        elif title.startswith("Telnet"):
            icon_name = "network-wired-symbolic"
        elif title.startswith("Serial"):
            icon_name = "media-removable-symbolic"
        else:
            icon_name = "utilities-terminal-symbolic"

        tab_icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
        tab_box.pack_start(tab_icon, False, False, 0)

        label = Gtk.Label(label=title)
        label.set_width_chars(_TAB_LABEL_MIN_CHARS)
        label.set_max_width_chars(_TAB_LABEL_MAX_CHARS)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_tooltip_text(title)
        tab_box.pack_start(label, True, True, 0)

        close_btn = Gtk.Button()
        close_icon = Gtk.Image.new_from_icon_name(
            "window-close-symbolic", Gtk.IconSize.MENU
        )
        close_btn.set_image(close_icon)
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        close_btn.connect("clicked", self._on_close_tab, terminal)
        tab_box.pack_end(close_btn, False, False, 0)
        tab_box.show_all()

        # Wrap in EventBox for right-click context menu
        tab_box_eventbox = Gtk.EventBox()
        tab_box_eventbox.add(tab_box)
        tab_box_eventbox.show_all()
        tab_box_eventbox.connect("button-press-event", self._on_tab_right_click, terminal)

        idx = self._notebook.append_page(terminal, tab_box_eventbox)
        self._notebook.set_tab_reorderable(terminal, True)
        terminal.show_all()
        self._notebook.set_current_page(idx)
        self._update_tab_count()

    def _on_close_tab(self, _btn, terminal):
        idx = self._notebook.page_num(terminal)
        if idx >= 0:
            self._notebook.remove_page(idx)
            self._update_tab_count()

    def _on_tab_switched(self, _notebook, page, _page_num):
        """Update the window title when tabs change."""
        if hasattr(page, "get_title"):
            self.set_title(f"{page.get_title()} — {__app_name__}")

    def _on_tab_right_click(self, widget, event, terminal):
        """Show context menu on right-click of a tab."""
        if event.button != 3:
            return False

        menu = Gtk.Menu()

        def _safe_call(func, *args):
            """Only invoke *func* if *terminal* is still in the notebook."""
            if self._notebook.page_num(terminal) >= 0:
                func(*args)

        # Close tab
        close_item = Gtk.MenuItem(label="Close")
        close_item.connect("activate", lambda _i: _safe_call(self._on_close_tab, None, terminal))
        menu.append(close_item)

        # Close other tabs
        close_others = Gtk.MenuItem(label="Close Others")
        close_others.connect("activate", lambda _i: _safe_call(self._close_other_tabs, terminal))
        menu.append(close_others)

        menu.append(Gtk.SeparatorMenuItem())

        # Duplicate tab
        dup_item = Gtk.MenuItem(label="Duplicate Tab")
        dup_item.connect("activate", lambda _i: self.add_local_terminal_tab())
        menu.append(dup_item)

        menu.append(Gtk.SeparatorMenuItem())

        # Split horizontal
        split_h = Gtk.MenuItem(label="Split Horizontal")
        split_h.connect("activate", lambda _i: _safe_call(self._split_terminal, terminal, Gtk.Orientation.HORIZONTAL))
        menu.append(split_h)

        # Split vertical
        split_v = Gtk.MenuItem(label="Split Vertical")
        split_v.connect("activate", lambda _i: _safe_call(self._split_terminal, terminal, Gtk.Orientation.VERTICAL))
        menu.append(split_v)

        menu.append(Gtk.SeparatorMenuItem())

        # Copy / Paste
        copy_item = Gtk.MenuItem(label="Copy")
        copy_item.connect("activate", lambda _i: _safe_call(terminal.copy_clipboard))
        menu.append(copy_item)

        paste_item = Gtk.MenuItem(label="Paste")
        paste_item.connect("activate", lambda _i: _safe_call(terminal.paste_clipboard))
        menu.append(paste_item)

        menu.show_all()
        # Keep a reference so Python's GC doesn't collect the menu while
        # GTK is still displaying it (prevents segfault).
        self._tab_context_menu = menu
        menu.popup(None, None, None, None, event.button, event.time)
        return True

    def _close_other_tabs(self, keep_terminal):
        """Close all tabs except the specified one."""
        pages_to_remove = []
        for i in range(self._notebook.get_n_pages()):
            page = self._notebook.get_nth_page(i)
            if page is not keep_terminal:
                pages_to_remove.append(page)
        for page in pages_to_remove:
            idx = self._notebook.page_num(page)
            if idx >= 0:
                self._notebook.remove_page(idx)
        self._update_tab_count()

    def _add_tab_at(self, widget, title: str, position: int = -1):
        """Insert a widget as a tab at a specific position (or end)."""
        self._tab_counter += 1
        tab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        tab_icon = Gtk.Image.new_from_icon_name(
            "view-dual-symbolic", Gtk.IconSize.MENU
        )
        tab_box.pack_start(tab_icon, False, False, 0)

        label = Gtk.Label(label=title)
        label.set_width_chars(_TAB_LABEL_MIN_CHARS)
        label.set_max_width_chars(_TAB_LABEL_MAX_CHARS)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_tooltip_text(title)
        tab_box.pack_start(label, True, True, 0)

        close_btn = Gtk.Button()
        close_icon = Gtk.Image.new_from_icon_name(
            "window-close-symbolic", Gtk.IconSize.MENU
        )
        close_btn.set_image(close_icon)
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        close_btn.connect("clicked", self._on_close_tab, widget)
        tab_box.pack_end(close_btn, False, False, 0)

        tab_eventbox = Gtk.EventBox()
        tab_eventbox.add(tab_box)
        tab_eventbox.show_all()

        if position >= 0:
            idx = self._notebook.insert_page(widget, tab_eventbox, position)
        else:
            idx = self._notebook.append_page(widget, tab_eventbox)
        self._notebook.set_tab_reorderable(widget, True)
        widget.show_all()
        self._notebook.set_current_page(idx)
        self._update_tab_count()

    def _split_terminal(self, terminal, orientation):
        """Split the current tab by adding a new terminal alongside."""
        # Find the notebook page containing this terminal
        idx = self._notebook.page_num(terminal)
        page_widget = terminal
        if idx < 0:
            # Terminal might be nested inside a Paned from a previous split
            parent = terminal.get_parent()
            while parent is not None and parent != self._notebook:
                test_idx = self._notebook.page_num(parent)
                if test_idx >= 0:
                    idx = test_idx
                    page_widget = parent
                    break
                parent = parent.get_parent()
        if idx < 0:
            return

        # Create new terminal
        settings = self._settings_mgr.settings
        new_terminal = TerminalWidget(settings=settings)

        # Create split pane
        paned = Gtk.Paned(orientation=orientation)

        # Remove page from notebook
        self._notebook.remove_page(idx)

        paned.pack1(page_widget, resize=True, shrink=False)
        paned.pack2(new_terminal, resize=True, shrink=False)
        page_widget.show_all()
        new_terminal.show_all()
        paned.show_all()

        # Re-insert at same position
        self._add_tab_at(paned, "Split View", idx)

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

    def _show_settings_dialog(self):
        """Show the Tabby-inspired application settings dialog."""
        dialog = Gtk.Dialog(
            title="Settings",
            transient_for=self,
            modal=True,
        )
        dialog.set_default_size(600, 500)
        dialog.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("_Apply", Gtk.ResponseType.OK)

        content = dialog.get_content_area()
        notebook = Gtk.Notebook()
        notebook.set_tab_pos(Gtk.PositionType.LEFT)
        content.pack_start(notebook, True, True, 0)

        s = self._settings_mgr.settings

        # --- Terminal Tab ---
        term_grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        term_grid.set_margin_start(16)
        term_grid.set_margin_end(16)
        term_grid.set_margin_top(16)
        term_grid.set_margin_bottom(16)

        row = 0

        def add_row(grid, label_text, widget, r):
            lbl = Gtk.Label(label=label_text)
            lbl.set_xalign(1)
            lbl.set_halign(Gtk.Align.END)
            grid.attach(lbl, 0, r, 1, 1)
            widget.set_hexpand(True)
            grid.attach(widget, 1, r, 1, 1)
            return r + 1

        # Font family
        font_entry = Gtk.Entry()
        font_entry.set_text(s.font_family)
        row = add_row(term_grid, "Font Family:", font_entry, row)

        # Font size
        font_size_spin = Gtk.SpinButton.new_with_range(6, 72, 1)
        font_size_spin.set_value(s.font_size)
        row = add_row(term_grid, "Font Size:", font_size_spin, row)

        # Scrollback lines
        scroll_spin = Gtk.SpinButton.new_with_range(100, 1000000, 100)
        scroll_spin.set_value(s.scrollback_lines)
        row = add_row(term_grid, "Scrollback Lines:", scroll_spin, row)

        # Cursor style
        cursor_combo = Gtk.ComboBoxText()
        for cid, clabel in [("block", "Block"), ("ibeam", "I-Beam"), ("underline", "Underline")]:
            cursor_combo.append(cid, clabel)
        cursor_combo.set_active_id(s.cursor_style)
        row = add_row(term_grid, "Cursor Style:", cursor_combo, row)

        # Cursor blink
        cursor_blink_check = Gtk.CheckButton(label="Enable cursor blinking")
        cursor_blink_check.set_active(s.cursor_blink)
        row = add_row(term_grid, "Cursor Blink:", cursor_blink_check, row)

        # Terminal bell
        bell_check = Gtk.CheckButton(label="Enable terminal bell")
        bell_check.set_active(s.terminal_bell)
        row = add_row(term_grid, "Terminal Bell:", bell_check, row)

        # Bold is bright
        bold_check = Gtk.CheckButton(label="Bold text appears bright")
        bold_check.set_active(s.bold_is_bright)
        row = add_row(term_grid, "Bold is Bright:", bold_check, row)

        # Copy on select
        copy_sel_check = Gtk.CheckButton(label="Copy text on selection")
        copy_sel_check.set_active(s.copy_on_select)
        row = add_row(term_grid, "Copy on Select:", copy_sel_check, row)

        notebook.append_page(term_grid, Gtk.Label(label="Terminal"))

        # --- Appearance Tab ---
        appear_grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        appear_grid.set_margin_start(16)
        appear_grid.set_margin_end(16)
        appear_grid.set_margin_top(16)
        appear_grid.set_margin_bottom(16)

        row = 0

        # Background color
        bg_entry = Gtk.Entry()
        bg_entry.set_text(s.terminal_bg_color)
        row = add_row(appear_grid, "Background Color:", bg_entry, row)

        # Foreground color
        fg_entry = Gtk.Entry()
        fg_entry.set_text(s.terminal_fg_color)
        row = add_row(appear_grid, "Foreground Color:", fg_entry, row)

        # Window width
        width_spin = Gtk.SpinButton.new_with_range(400, 4000, 10)
        width_spin.set_value(s.window_width)
        row = add_row(appear_grid, "Window Width:", width_spin, row)

        # Window height
        height_spin = Gtk.SpinButton.new_with_range(300, 3000, 10)
        height_spin.set_value(s.window_height)
        row = add_row(appear_grid, "Window Height:", height_spin, row)

        # Tab position
        tab_pos_combo = Gtk.ComboBoxText()
        for pid, plabel in [("left", "Left"), ("top", "Top"), ("bottom", "Bottom"), ("right", "Right")]:
            tab_pos_combo.append(pid, plabel)
        tab_pos_combo.set_active_id(s.tab_position)
        row = add_row(appear_grid, "Tab Position:", tab_pos_combo, row)

        notebook.append_page(appear_grid, Gtk.Label(label="Appearance"))

        # --- General Tab ---
        general_grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        general_grid.set_margin_start(16)
        general_grid.set_margin_end(16)
        general_grid.set_margin_top(16)
        general_grid.set_margin_bottom(16)

        row = 0

        # Show sidebar
        sidebar_check = Gtk.CheckButton(label="Show sidebar on startup")
        sidebar_check.set_active(s.show_sidebar)
        row = add_row(general_grid, "Sidebar:", sidebar_check, row)

        # Confirm close
        confirm_check = Gtk.CheckButton(label="Confirm before closing tabs")
        confirm_check.set_active(s.confirm_close_tab)
        row = add_row(general_grid, "Confirm Close:", confirm_check, row)

        notebook.append_page(general_grid, Gtk.Label(label="General"))

        dialog.show_all()

        if dialog.run() == Gtk.ResponseType.OK:
            # Apply settings
            s.font_family = font_entry.get_text().strip() or "Monospace"
            s.font_size = int(font_size_spin.get_value())
            s.scrollback_lines = int(scroll_spin.get_value())
            s.cursor_style = cursor_combo.get_active_id() or "block"
            s.cursor_blink = cursor_blink_check.get_active()
            s.terminal_bell = bell_check.get_active()
            s.bold_is_bright = bold_check.get_active()
            s.copy_on_select = copy_sel_check.get_active()
            s.terminal_bg_color = bg_entry.get_text().strip() or "#1e1e2e"
            s.terminal_fg_color = fg_entry.get_text().strip() or "#cdd6f4"
            s.window_width = int(width_spin.get_value())
            s.window_height = int(height_spin.get_value())
            s.tab_position = tab_pos_combo.get_active_id() or "left"
            s.show_sidebar = sidebar_check.get_active()
            s.confirm_close_tab = confirm_check.get_active()

            self._settings_mgr.save()
            self._apply_tab_position()
            self._push_status("Settings saved")

        dialog.destroy()

    def _apply_tab_position(self):
        """Apply the tab position setting to the notebook."""
        pos_map = {
            "left": Gtk.PositionType.LEFT,
            "top": Gtk.PositionType.TOP,
            "bottom": Gtk.PositionType.BOTTOM,
            "right": Gtk.PositionType.RIGHT,
        }
        pos = pos_map.get(
            self._settings_mgr.settings.tab_position, Gtk.PositionType.TOP
        )
        self._notebook.set_tab_pos(pos)

    # ======================================================================
    # View toggles
    # ======================================================================

    def _on_toggle_sidebar(self, item):
        if item.get_active():
            self._sidebar_frame.show()
        else:
            self._sidebar_frame.hide()
        self._settings_mgr.settings.show_sidebar = item.get_active()

    def _on_toggle_multi(self, item):
        if item.get_active():
            self._multi_exec.show()
            self._multi_exec.enabled = True
        else:
            self._multi_exec.hide()
            self._multi_exec.enabled = False

    def _on_toggle_sftp(self, item):
        if item.get_active():
            self._show_sftp_pane()
        else:
            self._hide_sftp_pane()

    def _show_sftp_pane(self):
        """Show the SFTP file browser panel below the sessions sidebar."""
        self._sftp_frame.show_all()
        self._sftp_visible = True
        # Position the vertical split so sessions and SFTP each get half
        alloc = self._left_vpaned.get_allocation()
        self._left_vpaned.set_position(alloc.height // 2)
        self._toggle_sftp.set_active(True)

    def _hide_sftp_pane(self):
        """Hide the SFTP file browser panel."""
        self._sftp_frame.hide()
        self._sftp_visible = False
        self._toggle_sftp.set_active(False)

    def _on_toggle_toolbar(self, item):
        """Toggle the toolbar visibility."""
        if item.get_active():
            self._toolbar.show()
        else:
            self._toolbar.hide()

    def _on_toggle_focus_mode(self, item):
        """Toggle focus mode — maximize terminal by hiding chrome."""
        self._focus_mode = item.get_active()
        if self._focus_mode:
            self._toolbar.hide()
            self._menubar.hide()
            self._left_vpaned.hide()
            self._statusbar.hide()
            self._toggle_toolbar.set_active(False)
        else:
            self._toolbar.show()
            self._menubar.show()
            self._left_vpaned.show()
            self._statusbar.show()
            self._toggle_toolbar.set_active(True)

    def _on_key_press(self, widget, event):
        """Handle keyboard shortcuts."""
        if event.keyval == Gdk.KEY_F11:
            self._focus_mode_item.set_active(not self._focus_mode)
            return True
        return False

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

    def _auto_enter_password(self, terminal: TerminalWidget, password: str):
        """Watch the terminal for a password prompt and auto-type the password.

        Uses a ``contents-changed`` signal on the VTE widget.  Once the
        prompt is detected (or after a maximum number of checks) the handler
        disconnects itself to avoid interfering with the session.
        """
        state = {"handler_id": None, "attempts": 0}

        def _on_contents_changed(vte_widget):
            state["attempts"] += 1
            # Give up after ~120 checks (~12 s at the default signal rate)
            if state["attempts"] > 120:
                vte_widget.disconnect(state["handler_id"])
                return
            # Read the last few rows of terminal output.
            # Use get_text_range_format (VTE ≥ 0.72) to avoid the
            # deprecated GArray attributes parameter; fall back to
            # get_text_range on older versions.
            col, row = vte_widget.get_cursor_position()
            start_row = max(0, row - 3)
            if hasattr(vte_widget, "get_text_range_format"):
                text = vte_widget.get_text_range_format(
                    Vte.Format.TEXT, start_row, 0, row, col
                )
            else:
                text = vte_widget.get_text_range(
                    start_row, 0, row, col, None
                )
            if text and isinstance(text, tuple):
                text = text[0]
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="replace")
            if text:
                lower = text.lower()
                if "password" in lower or "passphrase" in lower:
                    vte_widget.feed_child(
                        (password + "\n").encode("utf-8")
                    )
                    vte_widget.disconnect(state["handler_id"])

        state["handler_id"] = terminal.vte.connect(
            "contents-changed", _on_contents_changed
        )

    def _apply_window_settings(self):
        s = self._settings_mgr.settings
        self.set_default_size(s.window_width, s.window_height)

    def _push_status(self, text: str):
        self._status_label.set_text(text)

    def _update_tab_count(self):
        """Update the tab count display in the status bar."""
        count = self._notebook.get_n_pages()
        self._tab_count_label.set_text(f"{count} tab{'s' if count != 1 else ''}")


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
