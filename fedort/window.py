"""Main application window for FedoRT.

Provides the primary :class:`MainWindow` – a SecureCRT-inspired GTK3
window that integrates every subsystem (terminal tabs, session sidebar,
SFTP browser, button bar, multi-exec bar, tunnels, macros, key mappings,
credential store, and network tools) into a cohesive, themeable UI.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Optional

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Vte", "2.91")

from gi.repository import Gdk, GLib, GObject, Gtk, Pango, Vte  # noqa: E402

from fedort import __version__  # noqa: E402
from fedort.button_bar import ButtonBarWidget  # noqa: E402
from fedort.multi_exec import MultiExecBar  # noqa: E402
from fedort.session_manager import SessionSidebar  # noqa: E402
from fedort.settings import (  # noqa: E402
    AppSettings,
    SettingsManager,
    SSHSession,
    dataclass_to_dict,
)
from fedort.sftp_browser import SFTPBrowser  # noqa: E402
from fedort.ssh_client import build_ssh_command, parse_connection_string  # noqa: E402
from fedort.terminal import TerminalWidget  # noqa: E402

logger = logging.getLogger(__name__)

# ── Tab-label sizing ────────────────────────────────────────────────
_TAB_LABEL_MIN_CHARS = 8
_TAB_LABEL_MAX_CHARS = 20

# ── Theme presets ───────────────────────────────────────────────────
_THEME_PRESETS: dict[str, dict[str, Any]] = {
    "Default": {
        "fg": "#d0d0d0",
        "bg": "#1e1e1e",
        "palette": [
            "#000000", "#cc0000", "#4e9a06", "#c4a000",
            "#3465a4", "#75507b", "#06989a", "#d3d7cf",
            "#555753", "#ef2929", "#8ae234", "#fce94f",
            "#729fcf", "#ad7fa8", "#34e2e2", "#eeeeec",
        ],
    },
    "Catppuccin Mocha": {
        "fg": "#cdd6f4",
        "bg": "#1e1e2e",
        "palette": [
            "#45475a", "#f38ba8", "#a6e3a1", "#f9e2af",
            "#89b4fa", "#f5c2e7", "#94e2d5", "#bac2de",
            "#585b70", "#f38ba8", "#a6e3a1", "#f9e2af",
            "#89b4fa", "#f5c2e7", "#94e2d5", "#a6adc8",
        ],
    },
    "Solarized Dark": {
        "fg": "#839496",
        "bg": "#002b36",
        "palette": [
            "#073642", "#dc322f", "#859900", "#b58900",
            "#268bd2", "#d33682", "#2aa198", "#eee8d5",
            "#002b36", "#cb4b16", "#586e75", "#657b83",
            "#839496", "#6c71c4", "#93a1a1", "#fdf6e3",
        ],
    },
    "Dracula": {
        "fg": "#f8f8f2",
        "bg": "#282a36",
        "palette": [
            "#21222c", "#ff5555", "#50fa7b", "#f1fa8c",
            "#bd93f9", "#ff79c6", "#8be9fd", "#f8f8f2",
            "#6272a4", "#ff6e6e", "#69ff94", "#ffffa5",
            "#d6acff", "#ff92df", "#a4ffff", "#ffffff",
        ],
    },
    "Nord": {
        "fg": "#d8dee9",
        "bg": "#2e3440",
        "palette": [
            "#3b4252", "#bf616a", "#a3be8c", "#ebcb8b",
            "#81a1c1", "#b48ead", "#88c0d0", "#e5e9f0",
            "#4c566a", "#bf616a", "#a3be8c", "#ebcb8b",
            "#81a1c1", "#b48ead", "#8fbcbb", "#eceff4",
        ],
    },
    "Gruvbox Dark": {
        "fg": "#ebdbb2",
        "bg": "#282828",
        "palette": [
            "#282828", "#cc241d", "#98971a", "#d79921",
            "#458588", "#b16286", "#689d6a", "#a89984",
            "#928374", "#fb4934", "#b8bb26", "#fabd2f",
            "#83a598", "#d3869b", "#8ec07c", "#ebdbb2",
        ],
    },
    "One Dark": {
        "fg": "#abb2bf",
        "bg": "#282c34",
        "palette": [
            "#282c34", "#e06c75", "#98c379", "#e5c07b",
            "#61afef", "#c678dd", "#56b6c2", "#abb2bf",
            "#545862", "#e06c75", "#98c379", "#e5c07b",
            "#61afef", "#c678dd", "#56b6c2", "#c8ccd4",
        ],
    },
    "Tango": {
        "fg": "#d3d7cf",
        "bg": "#2e3436",
        "palette": [
            "#2e3436", "#cc0000", "#4e9a06", "#c4a000",
            "#3465a4", "#75507b", "#06989a", "#d3d7cf",
            "#555753", "#ef2929", "#8ae234", "#fce94f",
            "#729fcf", "#ad7fa8", "#34e2e2", "#eeeeec",
        ],
    },
}

# ── Tab-position mapping ────────────────────────────────────────────
_TAB_POS_MAP: dict[str, Gtk.PositionType] = {
    "top": Gtk.PositionType.TOP,
    "bottom": Gtk.PositionType.BOTTOM,
    "left": Gtk.PositionType.LEFT,
    "right": Gtk.PositionType.RIGHT,
}

# ── CSS ─────────────────────────────────────────────────────────────
# Avoid ``transition: all`` and ``box-shadow: inset`` which can segfault
# in some GTK3 builds.

_APP_CSS = """
/* ── Headerbar ──────────────────────────────────────────── */
headerbar {
    min-height: 28px;
    padding: 0 4px;
    background: #2b2b2b;
    border-bottom: 1px solid #1a1a1a;
    color: #f5f5f7;
}

/* ── Toolbar ────────────────────────────────────────────── */
.toolbar-compact {
    padding: 1px 4px;
    background: #2b2b2b;
    border-bottom: 1px solid #1a1a1a;
}
.toolbar-compact button {
    padding: 2px 4px;
    min-height: 20px;
    min-width: 20px;
    background: transparent;
    border: none;
    color: #d0d0d0;
}
.toolbar-compact button:hover {
    background: rgba(255,255,255,0.08);
    border-radius: 4px;
}

/* ── Notebook tabs ──────────────────────────────────────── */
notebook header {
    background: #2b2b2b;
    border-bottom: 1px solid #1a1a1a;
}
notebook header tabs tab {
    padding: 4px 10px;
    margin: 0;
    border-radius: 6px 6px 0 0;
    background: #333;
    color: #aaa;
    min-width: 60px;
}
notebook header tabs tab:checked {
    background: #1e1e1e;
    color: #f5f5f7;
    border-bottom: 2px solid #007aff;
}

/* ── Sidebar ────────────────────────────────────────────── */
.sidebar-pane {
    background: #252525;
}
.sidebar-pane treeview {
    background: #252525;
    color: #d0d0d0;
}

/* ── Status bar ─────────────────────────────────────────── */
.statusbar {
    background: #2b2b2b;
    border-top: 1px solid #1a1a1a;
    padding: 2px 8px;
    color: #888;
    font-size: 11px;
}

/* ── Menu bar ───────────────────────────────────────────── */
menubar {
    background: #2b2b2b;
    color: #d0d0d0;
    border-bottom: 1px solid #1a1a1a;
    padding: 0;
}
menubar > menuitem {
    padding: 4px 8px;
    color: #d0d0d0;
}
menubar > menuitem:hover {
    background: rgba(255,255,255,0.08);
}

/* ── Dialog labels ──────────────────────────────────────── */
dialog label {
    color: #f5f5f7;
}
dialog entry {
    background: #333;
    color: #f5f5f7;
    border: 1px solid #555;
}
dialog notebook tab {
    color: #d0d0d0;
}
dialog notebook tab:checked {
    color: #f5f5f7;
}

/* ── Button bar ─────────────────────────────────────────── */
.button-bar {
    background: #2b2b2b;
    border-top: 1px solid #1a1a1a;
    padding: 2px 4px;
}
"""


def _load_css() -> None:
    """Load application-wide CSS, swallowing errors gracefully."""
    try:
        provider = Gtk.CssProvider()
        provider.load_from_data(_APP_CSS.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
    except Exception:
        logger.exception("Failed to load application CSS")


# ── MainWindow ──────────────────────────────────────────────────────


class MainWindow(Gtk.ApplicationWindow):
    """Full-featured SecureCRT-style terminal window.

    Integrates the session sidebar, SFTP browser, terminal notebook,
    button bar, multi-exec bar, and status bar into a 3-pane layout
    with a dark theme, menu bar, toolbar, and settings dialog.
    """

    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="FedoRT")

        # ── Settings ────────────────────────────────────────────────
        self._settings_mgr = SettingsManager()
        self._settings: AppSettings = self._settings_mgr.load()

        self.set_default_size(
            self._settings.window_width,
            self._settings.window_height,
        )

        # ── State ───────────────────────────────────────────────────
        self._focus_mode: bool = False
        self._tab_counter: int = 0
        self._tab_context_menu: Optional[Gtk.Menu] = None

        # ── Load CSS ────────────────────────────────────────────────
        _load_css()

        # ── Build UI ────────────────────────────────────────────────
        self._vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(self._vbox)

        self._build_menubar()
        self._build_toolbar()
        self._build_main_area()
        self._build_button_bar()
        self._build_multi_exec_bar()
        self._build_statusbar()

        # ── Apply settings visibility ───────────────────────────────
        self._apply_ui_visibility()

        # ── Wire signals ────────────────────────────────────────────
        self._wire_signals()

        # ── Load persisted sessions into sidebar ────────────────────
        sessions = self._settings_mgr.load_sessions()
        self._sidebar.load_sessions(sessions)

        # ── Open an initial local terminal tab ──────────────────────
        self._add_local_tab()

        # ── Keyboard shortcuts ──────────────────────────────────────
        self.connect("key-press-event", self._on_key_press)

        self.show_all()

        # Reapply visibility *after* show_all to ensure hidden items stay hidden.
        self._apply_ui_visibility()

    # ================================================================
    #  Menu bar
    # ================================================================

    def _build_menubar(self) -> None:
        """Construct the main menu bar."""
        self._menubar = Gtk.MenuBar()

        # ── File ────────────────────────────────────────────────────
        file_menu = Gtk.Menu()
        self._add_menu_item(file_menu, "New _Terminal", self._on_new_tab)
        file_menu.append(Gtk.SeparatorMenuItem())
        self._add_menu_item(file_menu, "_Quick Connect\u2026", self._on_quick_connect)
        self._add_menu_item(file_menu, "_Connect in Tab\u2026", self._on_connect_in_tab)
        file_menu.append(Gtk.SeparatorMenuItem())
        self._add_menu_item(file_menu, "_Close Tab", self._on_close_tab)
        file_menu.append(Gtk.SeparatorMenuItem())
        self._add_menu_item(file_menu, "_Quit", lambda *_a: self.get_application().quit())
        file_item = Gtk.MenuItem(label="_File", use_underline=True)
        file_item.set_submenu(file_menu)
        self._menubar.append(file_item)

        # ── Edit ────────────────────────────────────────────────────
        edit_menu = Gtk.Menu()
        self._add_menu_item(edit_menu, "_Copy", lambda *_a: self._terminal_action("copy_text"))
        self._add_menu_item(edit_menu, "_Paste", lambda *_a: self._terminal_action("paste_text"))
        self._add_menu_item(edit_menu, "Select _All", lambda *_a: self._terminal_action("select_all"))
        edit_menu.append(Gtk.SeparatorMenuItem())
        self._add_menu_item(edit_menu, "_Find\u2026", self._on_find)
        edit_menu.append(Gtk.SeparatorMenuItem())
        self._add_menu_item(edit_menu, "_Reset Terminal", lambda *_a: self._terminal_action("reset_terminal"))
        edit_item = Gtk.MenuItem(label="_Edit", use_underline=True)
        edit_item.set_submenu(edit_menu)
        self._menubar.append(edit_item)

        # ── View ────────────────────────────────────────────────────
        view_menu = Gtk.Menu()
        self._view_toolbar_item = Gtk.CheckMenuItem(label="Show _Toolbar")
        self._view_toolbar_item.set_active(self._settings.show_toolbar)
        self._view_toolbar_item.connect("toggled", self._on_toggle_toolbar)
        view_menu.append(self._view_toolbar_item)

        self._view_menubar_item = Gtk.CheckMenuItem(label="Show _Menu Bar")
        self._view_menubar_item.set_active(self._settings.show_menubar)
        self._view_menubar_item.connect("toggled", self._on_toggle_menubar)
        view_menu.append(self._view_menubar_item)

        self._view_sidebar_item = Gtk.CheckMenuItem(label="Show _Sidebar")
        self._view_sidebar_item.set_active(self._settings.show_sidebar)
        self._view_sidebar_item.connect("toggled", self._on_toggle_sidebar)
        view_menu.append(self._view_sidebar_item)

        self._view_statusbar_item = Gtk.CheckMenuItem(label="Show S_tatus Bar")
        self._view_statusbar_item.set_active(self._settings.show_statusbar)
        self._view_statusbar_item.connect("toggled", self._on_toggle_statusbar)
        view_menu.append(self._view_statusbar_item)

        view_menu.append(Gtk.SeparatorMenuItem())

        self._add_menu_item(view_menu, "Zoom _In", lambda *_a: self._terminal_action("zoom_in"))
        self._add_menu_item(view_menu, "Zoom _Out", lambda *_a: self._terminal_action("zoom_out"))
        self._add_menu_item(view_menu, "Zoom _Reset", lambda *_a: self._terminal_action("zoom_reset"))

        view_menu.append(Gtk.SeparatorMenuItem())

        self._add_menu_item(view_menu, "_Focus Mode (F11)", self._toggle_focus_mode)

        view_item = Gtk.MenuItem(label="_View", use_underline=True)
        view_item.set_submenu(view_menu)
        self._menubar.append(view_item)

        # ── Tools ───────────────────────────────────────────────────
        tools_menu = Gtk.Menu()
        self._add_menu_item(tools_menu, "_Settings\u2026", self._show_settings_dialog)
        tools_menu.append(Gtk.SeparatorMenuItem())
        self._add_menu_item(tools_menu, "_Key Manager\u2026", self._show_key_manager)
        self._add_menu_item(tools_menu, "_Credential Store\u2026", self._show_credential_store)
        tools_menu.append(Gtk.SeparatorMenuItem())
        self._add_menu_item(tools_menu, "_Network Tools\u2026", self._show_network_tools)
        self._add_menu_item(tools_menu, "Tunnel _Manager\u2026", self._show_tunnel_manager)
        tools_menu.append(Gtk.SeparatorMenuItem())
        self._add_menu_item(tools_menu, "_Macro Manager\u2026", self._show_macro_manager)
        self._add_menu_item(tools_menu, "Key M_appings\u2026", self._show_key_mappings)
        tools_menu.append(Gtk.SeparatorMenuItem())
        self._add_menu_item(tools_menu, "Text _Editor", self._show_text_editor)

        tools_item = Gtk.MenuItem(label="_Tools", use_underline=True)
        tools_item.set_submenu(tools_menu)
        self._menubar.append(tools_item)

        # ── Session ─────────────────────────────────────────────────
        session_menu = Gtk.Menu()
        self._add_menu_item(session_menu, "_Toggle Logging", self._on_toggle_logging)
        session_menu.append(Gtk.SeparatorMenuItem())
        self._add_menu_item(session_menu, "Send _Break", lambda *_a: self._terminal_action("feed_command", "\x03"))
        self._add_menu_item(session_menu, "_Reconnect", self._on_reconnect)

        session_item = Gtk.MenuItem(label="_Session", use_underline=True)
        session_item.set_submenu(session_menu)
        self._menubar.append(session_item)

        # ── Window ──────────────────────────────────────────────────
        window_menu = Gtk.Menu()
        self._add_menu_item(window_menu, "_Next Tab", self._on_next_tab)
        self._add_menu_item(window_menu, "_Previous Tab", self._on_prev_tab)

        window_item = Gtk.MenuItem(label="_Window", use_underline=True)
        window_item.set_submenu(window_menu)
        self._menubar.append(window_item)

        # ── Help ────────────────────────────────────────────────────
        help_menu = Gtk.Menu()
        self._add_menu_item(help_menu, "_About", self._show_about)
        help_item = Gtk.MenuItem(label="_Help", use_underline=True)
        help_item.set_submenu(help_menu)
        self._menubar.append(help_item)

        self._vbox.pack_start(self._menubar, expand=False, fill=False, padding=0)

    @staticmethod
    def _add_menu_item(
        menu: Gtk.Menu,
        label: str,
        callback: object,
    ) -> Gtk.MenuItem:
        """Helper to add a menu item with a callback."""
        item = Gtk.MenuItem(label=label, use_underline=True)
        item.connect("activate", callback)
        menu.append(item)
        return item

    # ================================================================
    #  Toolbar
    # ================================================================

    def _build_toolbar(self) -> None:
        """Build the compact icon toolbar."""
        self._toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self._toolbar.get_style_context().add_class("toolbar-compact")

        toolbar_items: list[tuple[str, str, object]] = [
            ("document-new", "New Tab", self._on_new_tab),
            ("network-server", "Quick Connect", self._on_quick_connect),
            ("edit-copy", "Copy", lambda *_a: self._terminal_action("copy_text")),
            ("edit-paste", "Paste", lambda *_a: self._terminal_action("paste_text")),
            ("edit-find", "Find", self._on_find),
            ("zoom-in", "Zoom In", lambda *_a: self._terminal_action("zoom_in")),
            ("zoom-out", "Zoom Out", lambda *_a: self._terminal_action("zoom_out")),
            ("preferences-system", "Settings", self._show_settings_dialog),
        ]

        for icon_name, tooltip, callback in toolbar_items:
            btn = Gtk.Button()
            try:
                image = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
            except Exception:
                image = Gtk.Image()
            btn.set_image(image)
            btn.set_tooltip_text(tooltip)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.connect("clicked", callback)
            self._toolbar.pack_start(btn, expand=False, fill=False, padding=0)

        self._vbox.pack_start(self._toolbar, expand=False, fill=False, padding=0)

    # ================================================================
    #  Main area (sidebar + notebook)
    # ================================================================

    def _build_main_area(self) -> None:
        """Build the horizontal paned: sidebar | notebook."""
        self._hpaned = Gtk.HPaned()

        # ── Left pane: sessions + SFTP ──────────────────────────────
        self._left_vpaned = Gtk.VPaned()

        self._sidebar = SessionSidebar()
        self._sidebar.set_size_request(100, -1)
        self._sidebar.get_style_context().add_class("sidebar-pane")
        self._left_vpaned.pack1(self._sidebar, resize=True, shrink=False)

        self._sftp_browser = SFTPBrowser()
        self._sftp_browser.set_size_request(100, -1)
        self._left_vpaned.pack2(self._sftp_browser, resize=True, shrink=True)

        self._hpaned.pack1(self._left_vpaned, resize=True, shrink=True)

        # ── Right pane: terminal notebook ───────────────────────────
        self._notebook = Gtk.Notebook()
        self._notebook.set_scrollable(True)
        self._notebook.set_show_border(False)

        # Apply tab position from settings.
        pos = _TAB_POS_MAP.get(self._settings.tab_position, Gtk.PositionType.TOP)
        self._notebook.set_tab_pos(pos)

        self._hpaned.pack2(self._notebook, resize=True, shrink=False)

        # Set sidebar width from settings.
        self._hpaned.set_position(self._settings.sidebar_width)

        # Set SFTP height from settings.
        self._left_vpaned.set_position(
            max(self._settings.window_height - self._settings.sftp_panel_height, 200)
        )

        self._vbox.pack_start(self._hpaned, expand=True, fill=True, padding=0)

    # ================================================================
    #  Button bar
    # ================================================================

    def _build_button_bar(self) -> None:
        """Build the button bar widget below the terminal area."""
        self._button_bar = ButtonBarWidget()
        self._button_bar.get_style_context().add_class("button-bar")

        # Load first button-bar config if available.
        bars = self._settings_mgr.load_button_bars()
        if bars:
            self._button_bar.load_config(bars[0])

        self._vbox.pack_start(self._button_bar, expand=False, fill=False, padding=0)

    # ================================================================
    #  Multi-exec bar
    # ================================================================

    def _build_multi_exec_bar(self) -> None:
        """Build the broadcast command bar."""
        self._multi_exec = MultiExecBar()
        self._vbox.pack_start(self._multi_exec, expand=False, fill=False, padding=0)

    # ================================================================
    #  Status bar
    # ================================================================

    def _build_statusbar(self) -> None:
        """Build the bottom status bar."""
        self._statusbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._statusbar.get_style_context().add_class("statusbar")

        self._status_label = Gtk.Label(label="Ready")
        self._status_label.set_xalign(0)
        self._statusbar.pack_start(self._status_label, expand=True, fill=True, padding=0)

        self._status_tab_label = Gtk.Label(label="")
        self._statusbar.pack_end(self._status_tab_label, expand=False, fill=False, padding=0)

        self._vbox.pack_start(self._statusbar, expand=False, fill=False, padding=0)

    # ================================================================
    #  Signal wiring
    # ================================================================

    def _wire_signals(self) -> None:
        """Connect signals from child widgets."""
        # Sidebar → connect session.
        self._sidebar.connect("session-activated", self._on_session_activated)
        self._sidebar.connect("session-connect", self._on_session_connect)

        # Notebook tab changes → status bar update.
        self._notebook.connect("switch-page", self._on_tab_switched)

        # Button bar → feed command to active terminal.
        self._button_bar.connect("send-command", self._on_button_bar_command)
        self._button_bar.connect("send-command-all", self._on_button_bar_command_all)

        # Multi-exec bar → broadcast.
        self._multi_exec.connect("send-command", self._on_multi_exec_command)

        # SFTP signals.
        self._sftp_browser.connect("file-downloaded", self._on_sftp_downloaded)
        self._sftp_browser.connect("file-uploaded", self._on_sftp_uploaded)
        self._sftp_browser.connect("connection-error", self._on_sftp_error)

        # Window close.
        self.connect("delete-event", self._on_delete_event)

    # ================================================================
    #  Tab management
    # ================================================================

    def _add_local_tab(self) -> None:
        """Open a new local shell tab."""
        settings = self._get_terminal_settings()
        terminal = TerminalWidget(settings=settings)
        terminal.connect("child-exited", self._on_child_exited_tab)
        self._tab_counter += 1
        title = f"Terminal {self._tab_counter}"
        self._append_tab(terminal, title)

    def _add_ssh_tab(self, session: SSHSession) -> None:
        """Open a tab connected via SSH using the given session."""
        settings = self._get_terminal_settings()
        terminal = TerminalWidget(settings=settings)
        cmd_list = build_ssh_command(session)
        command = " ".join(cmd_list)
        terminal.spawn_shell(command=command)
        terminal.connect("child-exited", self._on_child_exited_tab)
        title = session.session_name or session.hostname or "SSH"
        self._append_tab(terminal, title)
        self._set_status(f"Connected to {session.hostname}")

        # Auto-connect SFTP if session is SSH.
        if session.protocol == "ssh2":
            self._sftp_browser.connect_to_server(
                hostname=session.hostname,
                port=session.port,
                username=session.username,
            )

    def _add_command_tab(self, command: str, title: str) -> None:
        """Open a tab running an arbitrary command."""
        settings = self._get_terminal_settings()
        terminal = TerminalWidget(settings=settings)
        terminal.spawn_shell(command=command)
        terminal.connect("child-exited", self._on_child_exited_tab)
        self._append_tab(terminal, title)

    def _append_tab(self, terminal: TerminalWidget, title: str) -> None:
        """Add a terminal widget as a new notebook tab."""
        tab_label = self._create_tab_label(title, terminal)
        idx = self._notebook.append_page(terminal, tab_label)
        self._notebook.set_current_page(idx)
        self._notebook.set_tab_reorderable(terminal, True)
        terminal.show_all()
        self._update_tab_count()

    def _create_tab_label(self, title: str, terminal: TerminalWidget) -> Gtk.Box:
        """Build a tab label with text and close button."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        label = Gtk.Label(label=title)
        label.set_width_chars(_TAB_LABEL_MIN_CHARS)
        label.set_max_width_chars(_TAB_LABEL_MAX_CHARS)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_tooltip_text(title)
        box.pack_start(label, expand=True, fill=True, padding=0)

        close_btn = Gtk.Button()
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        close_btn.set_focus_on_click(False)
        try:
            close_img = Gtk.Image.new_from_icon_name("window-close", Gtk.IconSize.MENU)
        except Exception:
            close_img = Gtk.Image()
        close_btn.set_image(close_img)
        close_btn.set_tooltip_text("Close tab")
        close_btn.connect("clicked", self._on_close_tab_button, terminal)
        box.pack_end(close_btn, expand=False, fill=False, padding=0)

        # Right-click context menu on tab.
        event_box = Gtk.EventBox()
        event_box.add(box)
        event_box.connect("button-press-event", self._on_tab_right_click, terminal)
        event_box.show_all()
        return event_box

    def _on_tab_right_click(
        self,
        widget: Gtk.Widget,
        event: Gdk.EventButton,
        terminal: TerminalWidget,
    ) -> bool:
        """Show context menu on tab right-click."""
        if event.button != 3:
            return False

        menu = Gtk.Menu()
        items: list[tuple[str, object]] = [
            ("Close Tab", lambda *_a: self._close_terminal_tab(terminal)),
            ("Close Other Tabs", lambda *_a: self._close_other_tabs(terminal)),
            ("Rename Tab\u2026", lambda *_a: self._rename_tab(terminal)),
        ]
        for label, callback in items:
            item = Gtk.MenuItem(label=label)
            item.connect("activate", callback)
            menu.append(item)
        menu.show_all()
        # Store to prevent GC.
        self._tab_context_menu = menu
        menu.popup(None, None, None, None, event.button, event.time)
        return True

    def _rename_tab(self, terminal: TerminalWidget) -> None:
        """Show a dialog to rename a tab."""
        page_num = self._notebook.page_num(terminal)
        if page_num < 0:
            return

        dialog = Gtk.Dialog(
            title="Rename Tab",
            transient_for=self,
            modal=True,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )

        content = dialog.get_content_area()
        entry = Gtk.Entry()
        # Get current label text.
        tab_widget = self._notebook.get_tab_label(terminal)
        if tab_widget:
            # tab_widget is the EventBox → Box → Label
            box = tab_widget.get_child()
            if box:
                for child in box.get_children():
                    if isinstance(child, Gtk.Label):
                        entry.set_text(child.get_text())
                        break
        content.pack_start(entry, expand=True, fill=True, padding=8)
        dialog.show_all()

        if dialog.run() == Gtk.ResponseType.OK:
            new_title = entry.get_text().strip()
            if new_title:
                self._set_tab_title(terminal, new_title)
        dialog.destroy()

    def _set_tab_title(self, terminal: TerminalWidget, title: str) -> None:
        """Update the label text for a tab."""
        tab_widget = self._notebook.get_tab_label(terminal)
        if not tab_widget:
            return
        box = tab_widget.get_child()
        if not box:
            return
        for child in box.get_children():
            if isinstance(child, Gtk.Label):
                child.set_text(title)
                child.set_tooltip_text(title)
                break

    def _close_terminal_tab(self, terminal: TerminalWidget) -> None:
        """Close a specific terminal tab."""
        page_num = self._notebook.page_num(terminal)
        if page_num >= 0:
            self._notebook.remove_page(page_num)
            self._update_tab_count()
            if self._notebook.get_n_pages() == 0:
                self._add_local_tab()

    def _close_other_tabs(self, keep: TerminalWidget) -> None:
        """Close all tabs except *keep*."""
        pages_to_close = []
        for i in range(self._notebook.get_n_pages()):
            child = self._notebook.get_nth_page(i)
            if child is not keep:
                pages_to_close.append(child)
        for child in pages_to_close:
            idx = self._notebook.page_num(child)
            if idx >= 0:
                self._notebook.remove_page(idx)
        self._update_tab_count()

    def _update_tab_count(self) -> None:
        """Update status bar tab count."""
        n = self._notebook.get_n_pages()
        self._status_tab_label.set_text(f"Tabs: {n}")

    # ================================================================
    #  Terminal settings enrichment
    # ================================================================

    def _get_terminal_settings(self) -> AppSettings:
        """Return a copy of settings enriched with theme palette."""
        settings = copy.copy(self._settings)
        theme_name = settings.theme
        theme = _THEME_PRESETS.get(theme_name, _THEME_PRESETS["Default"])
        # Attach palette data so TerminalWidget.apply_settings can use it.
        settings._palette = theme["palette"]  # type: ignore[attr-defined]
        settings._fg = theme["fg"]  # type: ignore[attr-defined]
        settings._bg = theme["bg"]  # type: ignore[attr-defined]
        return settings

    # ================================================================
    #  UI visibility helpers
    # ================================================================

    def _apply_ui_visibility(self) -> None:
        """Apply visibility of UI elements from settings."""
        if self._settings.show_toolbar:
            self._toolbar.show()
        else:
            self._toolbar.hide()

        if self._settings.show_menubar:
            self._menubar.show()
        else:
            self._menubar.hide()

        if self._settings.show_sidebar:
            self._left_vpaned.show()
        else:
            self._left_vpaned.hide()

        if self._settings.show_statusbar:
            self._statusbar.show()
        else:
            self._statusbar.hide()

    # ================================================================
    #  View toggles
    # ================================================================

    def _on_toggle_toolbar(self, item: Gtk.CheckMenuItem) -> None:
        self._settings.show_toolbar = item.get_active()
        self._apply_ui_visibility()

    def _on_toggle_menubar(self, item: Gtk.CheckMenuItem) -> None:
        self._settings.show_menubar = item.get_active()
        self._apply_ui_visibility()

    def _on_toggle_sidebar(self, item: Gtk.CheckMenuItem) -> None:
        self._settings.show_sidebar = item.get_active()
        self._apply_ui_visibility()

    def _on_toggle_statusbar(self, item: Gtk.CheckMenuItem) -> None:
        self._settings.show_statusbar = item.get_active()
        self._apply_ui_visibility()

    # ================================================================
    #  Focus mode
    # ================================================================

    def _toggle_focus_mode(self, *_args: object) -> None:
        """Toggle focus mode – hides everything except the terminal."""
        self._focus_mode = not self._focus_mode
        if self._focus_mode:
            self._toolbar.hide()
            self._menubar.hide()
            self._left_vpaned.hide()
            self._statusbar.hide()
            self._button_bar.hide()
            self._multi_exec.hide()
        else:
            self._apply_ui_visibility()
            self._button_bar.show()
            self._multi_exec.show()

    # ================================================================
    #  Keyboard shortcuts
    # ================================================================

    def _on_key_press(self, _widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        """Handle global keyboard shortcuts."""
        keyval = event.keyval
        state = event.state & (
            Gdk.ModifierType.CONTROL_MASK
            | Gdk.ModifierType.SHIFT_MASK
            | Gdk.ModifierType.MOD1_MASK
        )

        ctrl_shift = (
            Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
        )

        # F11 → focus mode.
        if keyval == Gdk.KEY_F11:
            self._toggle_focus_mode()
            return True

        # Ctrl+Shift+C → copy.
        if state == ctrl_shift and keyval in (Gdk.KEY_C, Gdk.KEY_c):
            self._terminal_action("copy_text")
            return True

        # Ctrl+Shift+V → paste.
        if state == ctrl_shift and keyval in (Gdk.KEY_V, Gdk.KEY_v):
            self._terminal_action("paste_text")
            return True

        # Ctrl+Shift+T → new tab.
        if state == ctrl_shift and keyval in (Gdk.KEY_T, Gdk.KEY_t):
            self._add_local_tab()
            return True

        # Ctrl+Shift+W → close tab.
        if state == ctrl_shift and keyval in (Gdk.KEY_W, Gdk.KEY_w):
            self._on_close_tab()
            return True

        # Ctrl+Shift+F → find.
        if state == ctrl_shift and keyval in (Gdk.KEY_F, Gdk.KEY_f):
            self._on_find()
            return True

        # Ctrl+Page_Down → next tab.
        if state & Gdk.ModifierType.CONTROL_MASK and keyval == Gdk.KEY_Page_Down:
            self._on_next_tab()
            return True

        # Ctrl+Page_Up → previous tab.
        if state & Gdk.ModifierType.CONTROL_MASK and keyval == Gdk.KEY_Page_Up:
            self._on_prev_tab()
            return True

        # Ctrl+Shift++ → zoom in.
        if state == ctrl_shift and keyval in (Gdk.KEY_plus, Gdk.KEY_equal):
            self._terminal_action("zoom_in")
            return True

        # Ctrl+- → zoom out.
        if state & Gdk.ModifierType.CONTROL_MASK and keyval == Gdk.KEY_minus:
            self._terminal_action("zoom_out")
            return True

        # Ctrl+0 → zoom reset.
        if state & Gdk.ModifierType.CONTROL_MASK and keyval == Gdk.KEY_0:
            self._terminal_action("zoom_reset")
            return True

        return False

    # ================================================================
    #  Active terminal helper
    # ================================================================

    def _get_active_terminal(self) -> Optional[TerminalWidget]:
        """Return the currently focused terminal widget, or ``None``."""
        page = self._notebook.get_current_page()
        if page < 0:
            return None
        child = self._notebook.get_nth_page(page)
        if isinstance(child, TerminalWidget):
            return child
        return None

    def _terminal_action(self, method: str, *args: object) -> None:
        """Call a method on the active terminal."""
        terminal = self._get_active_terminal()
        if terminal is not None:
            getattr(terminal, method)(*args)

    # ================================================================
    #  Signal handlers – sidebar
    # ================================================================

    def _on_session_activated(self, _widget: Gtk.Widget, session: SSHSession) -> None:
        """Connect to a session that was double-clicked in the sidebar."""
        self._add_ssh_tab(session)

    def _on_session_connect(
        self,
        _widget: Gtk.Widget,
        hostname: str,
        port: int,
        username: str,
    ) -> None:
        """Quick-connect from the sidebar."""
        session = SSHSession(hostname=hostname, port=port, username=username)
        self._add_ssh_tab(session)

    # ================================================================
    #  Signal handlers – button bar & multi-exec
    # ================================================================

    def _on_button_bar_command(self, _widget: Gtk.Widget, command: str) -> None:
        """Send a button-bar command to the active terminal."""
        terminal = self._get_active_terminal()
        if terminal is not None:
            terminal.feed_command(command + "\n")

    def _on_button_bar_command_all(self, _widget: Gtk.Widget, command: str) -> None:
        """Broadcast a button-bar command to all terminals."""
        self._broadcast_command(command)

    def _on_multi_exec_command(self, _widget: Gtk.Widget, command: str) -> None:
        """Send multi-exec command to terminals."""
        if self._multi_exec.broadcasting:
            self._broadcast_command(command)
        else:
            terminal = self._get_active_terminal()
            if terminal is not None:
                terminal.feed_command(command + "\n")

    def _broadcast_command(self, command: str) -> None:
        """Send a command to all open terminal tabs."""
        for i in range(self._notebook.get_n_pages()):
            child = self._notebook.get_nth_page(i)
            if isinstance(child, TerminalWidget):
                child.feed_command(command + "\n")

    # ================================================================
    #  Signal handlers – SFTP
    # ================================================================

    def _on_sftp_downloaded(self, _w: Gtk.Widget, remote: str, local: str) -> None:
        self._set_status(f"Downloaded: {remote} → {local}")

    def _on_sftp_uploaded(self, _w: Gtk.Widget, local: str, remote: str) -> None:
        self._set_status(f"Uploaded: {local} → {remote}")

    def _on_sftp_error(self, _w: Gtk.Widget, message: str) -> None:
        self._set_status(f"SFTP Error: {message}")

    # ================================================================
    #  Signal handlers – notebook / tabs
    # ================================================================

    def _on_tab_switched(self, _nb: Gtk.Notebook, _page: Gtk.Widget, page_num: int) -> None:
        terminal = self._notebook.get_nth_page(page_num)
        if isinstance(terminal, TerminalWidget):
            title = terminal.get_title()
            if title:
                self.set_title(f"{title} – FedoRT")
            else:
                self.set_title("FedoRT")

    def _on_child_exited_tab(self, terminal: Vte.Terminal, _status: int) -> None:
        """Handle a terminal's child process exiting."""
        # Find the TerminalWidget that wraps this VTE.
        for i in range(self._notebook.get_n_pages()):
            child = self._notebook.get_nth_page(i)
            if child is terminal or (isinstance(child, TerminalWidget) and not child.is_alive()):
                if self._settings.close_on_disconnect:
                    self._close_terminal_tab(child)
                else:
                    self._set_tab_title(child, "(disconnected)")
                break

    # ================================================================
    #  Menu callbacks
    # ================================================================

    def _on_new_tab(self, *_args: object) -> None:
        self._add_local_tab()

    def _on_close_tab(self, *_args: object) -> None:
        terminal = self._get_active_terminal()
        if terminal is not None:
            self._close_terminal_tab(terminal)

    def _on_close_tab_button(self, _btn: Gtk.Button, terminal: TerminalWidget) -> None:
        self._close_terminal_tab(terminal)

    def _on_next_tab(self, *_args: object) -> None:
        current = self._notebook.get_current_page()
        n = self._notebook.get_n_pages()
        if n > 0:
            self._notebook.set_current_page((current + 1) % n)

    def _on_prev_tab(self, *_args: object) -> None:
        current = self._notebook.get_current_page()
        n = self._notebook.get_n_pages()
        if n > 0:
            self._notebook.set_current_page((current - 1) % n)

    def _on_find(self, *_args: object) -> None:
        """Open a find dialog for the active terminal."""
        terminal = self._get_active_terminal()
        if terminal is None:
            return

        dialog = Gtk.Dialog(
            title="Find",
            transient_for=self,
            modal=True,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_FIND, Gtk.ResponseType.OK,
        )

        content = dialog.get_content_area()
        entry = Gtk.Entry()
        entry.set_placeholder_text("Search text\u2026")
        content.pack_start(entry, expand=True, fill=True, padding=8)

        regex_check = Gtk.CheckButton(label="Regular expression")
        content.pack_start(regex_check, expand=False, fill=False, padding=4)

        case_check = Gtk.CheckButton(label="Case sensitive")
        case_check.set_active(True)
        content.pack_start(case_check, expand=False, fill=False, padding=4)

        dialog.show_all()

        if dialog.run() == Gtk.ResponseType.OK:
            pattern = entry.get_text()
            if pattern:
                terminal.search_text(
                    pattern,
                    regex=regex_check.get_active(),
                    case_sensitive=case_check.get_active(),
                )
                terminal.search_next()

        dialog.destroy()

    def _on_quick_connect(self, *_args: object) -> None:
        """Show a quick-connect dialog."""
        dialog = Gtk.Dialog(
            title="Quick Connect",
            transient_for=self,
            modal=True,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_CONNECT, Gtk.ResponseType.OK,
        )

        content = dialog.get_content_area()
        content.set_spacing(8)
        content.set_border_width(12)

        # Connection string entry.
        lbl = Gtk.Label(label="Connection (user@host:port):")
        lbl.set_xalign(0)
        content.pack_start(lbl, expand=False, fill=False, padding=0)

        entry = Gtk.Entry()
        entry.set_placeholder_text("user@hostname:22")
        content.pack_start(entry, expand=False, fill=False, padding=0)

        dialog.show_all()

        if dialog.run() == Gtk.ResponseType.OK:
            text = entry.get_text().strip()
            if text:
                try:
                    host, port, user = parse_connection_string(text)
                    session = SSHSession(hostname=host, port=port, username=user)
                    self._add_ssh_tab(session)
                except (ValueError, TypeError):
                    self._set_status(f"Invalid connection string: {text}")
        dialog.destroy()

    def _on_connect_in_tab(self, *_args: object) -> None:
        """Re-use quick connect for now."""
        self._on_quick_connect()

    def _on_toggle_logging(self, *_args: object) -> None:
        """Toggle session logging for the active terminal."""
        terminal = self._get_active_terminal()
        if terminal is None:
            return
        # Simple toggle.
        if terminal._logging_enabled:
            terminal.set_logging(False)
            self._set_status("Logging stopped")
        else:
            import tempfile
            import datetime
            log_dir = self._settings.log_directory or tempfile.gettempdir()
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"{log_dir}/fedort_{ts}.log"
            terminal.set_logging(True, log_file_path=path)
            self._set_status(f"Logging to {path}")

    def _on_reconnect(self, *_args: object) -> None:
        """Reconnect the active terminal."""
        terminal = self._get_active_terminal()
        if terminal is not None:
            terminal.spawn_shell()
            self._set_status("Reconnected")

    # ================================================================
    #  Settings dialog
    # ================================================================

    def _show_settings_dialog(self, *_args: object) -> None:
        """Open a multi-tab settings dialog."""
        dialog = Gtk.Dialog(
            title="Settings",
            transient_for=self,
            modal=True,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        dialog.set_default_size(500, 400)

        content = dialog.get_content_area()
        content.set_border_width(8)

        notebook = Gtk.Notebook()
        content.pack_start(notebook, expand=True, fill=True, padding=0)

        # ── Terminal tab ────────────────────────────────────────────
        term_grid = Gtk.Grid()
        term_grid.set_row_spacing(8)
        term_grid.set_column_spacing(12)
        term_grid.set_border_width(12)

        row = 0
        font_lbl = Gtk.Label(label="Font Family:")
        font_lbl.set_xalign(0)
        font_entry = Gtk.Entry()
        font_entry.set_text(self._settings.font_family)
        term_grid.attach(font_lbl, 0, row, 1, 1)
        term_grid.attach(font_entry, 1, row, 1, 1)

        row += 1
        size_lbl = Gtk.Label(label="Font Size:")
        size_lbl.set_xalign(0)
        size_spin = Gtk.SpinButton.new_with_range(6, 72, 1)
        size_spin.set_value(self._settings.font_size)
        term_grid.attach(size_lbl, 0, row, 1, 1)
        term_grid.attach(size_spin, 1, row, 1, 1)

        row += 1
        scroll_lbl = Gtk.Label(label="Scrollback Lines:")
        scroll_lbl.set_xalign(0)
        scroll_spin = Gtk.SpinButton.new_with_range(100, 1000000, 1000)
        scroll_spin.set_value(self._settings.scrollback_lines)
        term_grid.attach(scroll_lbl, 0, row, 1, 1)
        term_grid.attach(scroll_spin, 1, row, 1, 1)

        row += 1
        cursor_lbl = Gtk.Label(label="Cursor Shape:")
        cursor_lbl.set_xalign(0)
        cursor_combo = Gtk.ComboBoxText()
        for shape in ("block", "ibeam", "underline"):
            cursor_combo.append_text(shape)
        cursor_combo.set_active(("block", "ibeam", "underline").index(self._settings.cursor_shape))
        term_grid.attach(cursor_lbl, 0, row, 1, 1)
        term_grid.attach(cursor_combo, 1, row, 1, 1)

        row += 1
        blink_chk = Gtk.CheckButton(label="Cursor Blink")
        blink_chk.set_active(self._settings.cursor_blink)
        term_grid.attach(blink_chk, 0, row, 2, 1)

        row += 1
        bell_chk = Gtk.CheckButton(label="Audible Bell")
        bell_chk.set_active(self._settings.audible_bell)
        term_grid.attach(bell_chk, 0, row, 2, 1)

        notebook.append_page(term_grid, Gtk.Label(label="Terminal"))

        # ── Appearance tab ──────────────────────────────────────────
        app_grid = Gtk.Grid()
        app_grid.set_row_spacing(8)
        app_grid.set_column_spacing(12)
        app_grid.set_border_width(12)

        row = 0
        theme_lbl = Gtk.Label(label="Theme:")
        theme_lbl.set_xalign(0)
        theme_combo = Gtk.ComboBoxText()
        theme_names = list(_THEME_PRESETS.keys())
        for name in theme_names:
            theme_combo.append_text(name)
        current_idx = theme_names.index(self._settings.theme) if self._settings.theme in theme_names else 0
        theme_combo.set_active(current_idx)
        app_grid.attach(theme_lbl, 0, row, 1, 1)
        app_grid.attach(theme_combo, 1, row, 1, 1)

        row += 1
        tabpos_lbl = Gtk.Label(label="Tab Position:")
        tabpos_lbl.set_xalign(0)
        tabpos_combo = Gtk.ComboBoxText()
        for pos in ("top", "bottom", "left", "right"):
            tabpos_combo.append_text(pos)
        tabpos_combo.set_active(("top", "bottom", "left", "right").index(self._settings.tab_position))
        app_grid.attach(tabpos_lbl, 0, row, 1, 1)
        app_grid.attach(tabpos_combo, 1, row, 1, 1)

        row += 1
        opacity_lbl = Gtk.Label(label="Opacity:")
        opacity_lbl.set_xalign(0)
        opacity_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.1, 1.0, 0.05)
        opacity_scale.set_value(self._settings.opacity)
        app_grid.attach(opacity_lbl, 0, row, 1, 1)
        app_grid.attach(opacity_scale, 1, row, 1, 1)

        notebook.append_page(app_grid, Gtk.Label(label="Appearance"))

        # ── General tab ─────────────────────────────────────────────
        gen_grid = Gtk.Grid()
        gen_grid.set_row_spacing(8)
        gen_grid.set_column_spacing(12)
        gen_grid.set_border_width(12)

        row = 0
        confirm_chk = Gtk.CheckButton(label="Confirm on Close")
        confirm_chk.set_active(self._settings.confirm_close)
        gen_grid.attach(confirm_chk, 0, row, 2, 1)

        row += 1
        close_disc_chk = Gtk.CheckButton(label="Close Tab on Disconnect")
        close_disc_chk.set_active(self._settings.close_on_disconnect)
        gen_grid.attach(close_disc_chk, 0, row, 2, 1)

        row += 1
        log_chk = Gtk.CheckButton(label="Log Sessions by Default")
        log_chk.set_active(self._settings.log_sessions)
        gen_grid.attach(log_chk, 0, row, 2, 1)

        row += 1
        logdir_lbl = Gtk.Label(label="Log Directory:")
        logdir_lbl.set_xalign(0)
        logdir_entry = Gtk.Entry()
        logdir_entry.set_text(self._settings.log_directory)
        gen_grid.attach(logdir_lbl, 0, row, 1, 1)
        gen_grid.attach(logdir_entry, 1, row, 1, 1)

        row += 1
        dldir_lbl = Gtk.Label(label="Download Directory:")
        dldir_lbl.set_xalign(0)
        dldir_entry = Gtk.Entry()
        dldir_entry.set_text(self._settings.default_download_dir)
        gen_grid.attach(dldir_lbl, 0, row, 1, 1)
        gen_grid.attach(dldir_entry, 1, row, 1, 1)

        notebook.append_page(gen_grid, Gtk.Label(label="General"))

        dialog.show_all()

        if dialog.run() == Gtk.ResponseType.OK:
            # Apply settings.
            self._settings.font_family = font_entry.get_text()
            self._settings.font_size = int(size_spin.get_value())
            self._settings.scrollback_lines = int(scroll_spin.get_value())
            self._settings.cursor_shape = cursor_combo.get_active_text() or "block"
            self._settings.cursor_blink = blink_chk.get_active()
            self._settings.audible_bell = bell_chk.get_active()
            self._settings.theme = theme_combo.get_active_text() or "Default"
            self._settings.tab_position = tabpos_combo.get_active_text() or "top"
            self._settings.opacity = opacity_scale.get_value()
            self._settings.confirm_close = confirm_chk.get_active()
            self._settings.close_on_disconnect = close_disc_chk.get_active()
            self._settings.log_sessions = log_chk.get_active()
            self._settings.log_directory = logdir_entry.get_text()
            self._settings.default_download_dir = dldir_entry.get_text()

            self._settings_mgr.settings = self._settings
            self._settings_mgr.save()
            self._apply_settings_to_terminals()

            # Update tab position.
            pos = _TAB_POS_MAP.get(self._settings.tab_position, Gtk.PositionType.TOP)
            self._notebook.set_tab_pos(pos)

        dialog.destroy()

    def _apply_settings_to_terminals(self) -> None:
        """Apply current settings to all open terminals."""
        settings = self._get_terminal_settings()
        for i in range(self._notebook.get_n_pages()):
            child = self._notebook.get_nth_page(i)
            if isinstance(child, TerminalWidget):
                child.apply_settings(settings)
                # Apply theme colours.
                theme = _THEME_PRESETS.get(self._settings.theme, _THEME_PRESETS["Default"])
                child.apply_colors(theme["fg"], theme["bg"], theme["palette"])

    # ================================================================
    #  Tool dialogs (stubs that show informational dialogs)
    # ================================================================

    def _show_tool_dialog(self, title: str, description: str) -> None:
        """Display a placeholder dialog for a tool."""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=title,
            secondary_text=description,
        )
        dialog.run()
        dialog.destroy()

    def _show_key_manager(self, *_args: object) -> None:
        """Open the SSH Key Manager dialog."""
        try:
            from fedort.key_manager import KeyManager
            mgr = KeyManager()
            keys = mgr.list_keys()
            info_text = f"Found {len(keys)} SSH key(s) in default directory."
            if keys:
                info_text += "\n\nKeys:\n" + "\n".join(
                    f"  • {k.path} ({k.key_type})" for k in keys
                )
            self._show_tool_dialog("SSH Key Manager", info_text)
        except Exception as exc:
            self._show_tool_dialog("SSH Key Manager", f"Error: {exc}")

    def _show_credential_store(self, *_args: object) -> None:
        """Open the Credential Store dialog."""
        try:
            from fedort.credential_store import CredentialStore
            store = CredentialStore()
            store.load()
            creds = store.list_credentials()
            info_text = f"Found {len(creds)} stored credential(s)."
            self._show_tool_dialog("Credential Store", info_text)
        except Exception as exc:
            self._show_tool_dialog("Credential Store", f"Error: {exc}")

    def _show_network_tools(self, *_args: object) -> None:
        """Open the Network Tools dialog."""
        self._show_tool_dialog(
            "Network Tools",
            "Network tools include Ping, Traceroute, NSLookup, Port Scanner, "
            "and Whois.\n\nUse the command-line tools directly in a terminal tab.",
        )

    def _show_tunnel_manager(self, *_args: object) -> None:
        """Open the Tunnel Manager dialog."""
        try:
            from fedort.tunnel_manager import TunnelManager
            mgr = TunnelManager()
            status = mgr.get_tunnel_status()
            count = len(status)
            info_text = f"Managing {count} tunnel(s)."
            self._show_tool_dialog("Tunnel Manager", info_text)
        except Exception as exc:
            self._show_tool_dialog("Tunnel Manager", f"Error: {exc}")

    def _show_macro_manager(self, *_args: object) -> None:
        """Open the Macro Manager dialog."""
        try:
            from fedort.macro_manager import MacroManager
            mgr = MacroManager()
            macros = mgr.list_macros()
            info_text = f"Found {len(macros)} macro(s)."
            if macros:
                info_text += "\n\nMacros:\n" + "\n".join(f"  • {m}" for m in macros)
            self._show_tool_dialog("Macro Manager", info_text)
        except Exception as exc:
            self._show_tool_dialog("Macro Manager", f"Error: {exc}")

    def _show_key_mappings(self, *_args: object) -> None:
        """Open the Key Mappings dialog."""
        try:
            from fedort.key_mappings import KeyMappingManager
            mgr = KeyMappingManager()
            mappings = mgr.list_mappings()
            info_text = f"Found {len(mappings)} key mapping(s)."
            if mappings:
                info_text += "\n\nMappings:\n" + "\n".join(
                    f"  • {m.key} → {m.action_type}: {m.action_value}" for m in mappings
                )
            self._show_tool_dialog("Key Mappings", info_text)
        except Exception as exc:
            self._show_tool_dialog("Key Mappings", f"Error: {exc}")

    def _show_text_editor(self, *_args: object) -> None:
        """Open the built-in text editor."""
        try:
            from fedort.text_editor import TextEditorDialog
            editor = TextEditorDialog(parent=self)
            editor.show_all()
        except Exception as exc:
            self._show_tool_dialog("Text Editor", f"Error: {exc}")

    def _show_about(self, *_args: object) -> None:
        """Show the About dialog."""
        about = Gtk.AboutDialog(
            transient_for=self,
            modal=True,
            program_name="FedoRT",
            version=__version__,
            comments="SecureCRT-compatible terminal emulator for Fedora Linux",
            license_type=Gtk.License.GPL_3_0,
            website="https://github.com/fedort/fedort",
            website_label="GitHub Repository",
            authors=["FedoRT Contributors"],
        )
        about.run()
        about.destroy()

    # ================================================================
    #  Status bar helper
    # ================================================================

    def _set_status(self, text: str) -> None:
        """Set the status bar text."""
        self._status_label.set_text(text)

    # ================================================================
    #  Window close
    # ================================================================

    def _on_delete_event(self, _widget: Gtk.Widget, _event: Gdk.Event) -> bool:
        """Handle window close, optionally confirming."""
        if self._settings.confirm_close and self._notebook.get_n_pages() > 1:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text="Close all tabs?",
                secondary_text=f"You have {self._notebook.get_n_pages()} open tabs.",
            )
            response = dialog.run()
            dialog.destroy()
            if response != Gtk.ResponseType.YES:
                return True  # Prevent close.

        # Persist window size.
        w, h = self.get_size()
        self._settings.window_width = w
        self._settings.window_height = h
        self._settings.sidebar_width = self._hpaned.get_position()
        self._settings_mgr.settings = self._settings
        self._settings_mgr.save()
        return False
