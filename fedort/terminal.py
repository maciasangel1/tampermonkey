"""VTE-based terminal widget for FedoRT.

Wraps :class:`Vte.Terminal` with full SecureCRT-compatible features
including search, logging, clipboard, zoom, and configurable appearance.
"""

from __future__ import annotations

import datetime
import logging
import os
from typing import TYPE_CHECKING, Optional

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")

from gi.repository import Gdk, GLib, Gtk, Pango, Vte  # noqa: E402

if TYPE_CHECKING:
    from fedort.settings import AppSettings

logger = logging.getLogger(__name__)

# ── Default colour palette (xterm-256 base-16) ─────────────────────

_DEFAULT_FG = "#d0d0d0"
_DEFAULT_BG = "#1e1e1e"
_DEFAULT_PALETTE = [
    "#000000", "#cc0000", "#4e9a06", "#c4a000",
    "#3465a4", "#75507b", "#06989a", "#d3d7cf",
    "#555753", "#ef2929", "#8ae234", "#fce94f",
    "#729fcf", "#ad7fa8", "#34e2e2", "#eeeeec",
]

# ── Mapping helpers ─────────────────────────────────────────────────

_CURSOR_SHAPE_MAP: dict[str, Vte.CursorShape] = {
    "block": Vte.CursorShape.BLOCK,
    "ibeam": Vte.CursorShape.IBEAM,
    "underline": Vte.CursorShape.UNDERLINE,
}


def _parse_rgba(color_str: str) -> Gdk.RGBA:
    """Parse a hex colour string into a :class:`Gdk.RGBA`."""
    rgba = Gdk.RGBA()
    rgba.parse(color_str)
    return rgba


# ── TerminalWidget ──────────────────────────────────────────────────


class TerminalWidget(Gtk.Box):
    """Composite widget containing a :class:`Vte.Terminal` and scrollbar.

    Parameters
    ----------
    settings:
        Optional :class:`AppSettings` instance.  When supplied the
        terminal appearance and behaviour are configured immediately.
    """

    def __init__(self, settings: Optional[AppSettings] = None) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)

        # ── VTE terminal ────────────────────────────────────────────
        self._vte: Vte.Terminal = Vte.Terminal()
        self.pack_start(self._vte, expand=True, fill=True, padding=0)

        # ── Scrollbar ───────────────────────────────────────────────
        self._scrollbar = Gtk.Scrollbar.new(
            Gtk.Orientation.VERTICAL, self._vte.get_vadjustment()
        )
        self.pack_start(self._scrollbar, expand=False, fill=False, padding=0)

        # ── Internal state ──────────────────────────────────────────
        self._child_pid: int = -1
        self._base_font_size: int = 12
        self._current_font_size: int = 12
        self._font_family: str = "Monospace"
        self._logging_enabled: bool = False
        self._log_file_path: Optional[str] = None
        self._log_format: str = "plain"
        self._log_timestamps: bool = False
        self._log_handler_id: Optional[int] = None
        self._context_menu: Optional[Gtk.Menu] = None

        # ── Signals ─────────────────────────────────────────────────
        self._vte.connect("child-exited", self._on_child_exited)
        self._vte.connect("window-title-changed", self._on_title_changed)
        self._vte.connect("button-press-event", self._on_button_press)

        # Apply supplied settings (if any) before spawning a shell.
        if settings is not None:
            self.apply_settings(settings)

        # Defer shell spawn until the widget is realised.
        self._vte.connect("realize", lambda *_a: self.spawn_shell())

    # ── Public signal helpers ───────────────────────────────────────

    def connect_child_exited(self, callback) -> int:
        """Connect *callback* to the inner VTE ``child-exited`` signal.

        The callback signature is ``callback(terminal_widget, status)``
        where *terminal_widget* is this :class:`TerminalWidget` instance.

        Returns the GObject signal handler id.
        """
        return self._vte.connect(
            "child-exited",
            lambda _vte, status: callback(self, status),
        )

    # ── Settings application ────────────────────────────────────────

    def apply_settings(self, settings: AppSettings) -> None:
        """Apply all relevant fields from *settings* to the terminal."""
        vte = self._vte

        # Font
        self._font_family = settings.font_family
        self._base_font_size = settings.font_size
        self._current_font_size = settings.font_size
        self._apply_font()

        # Scrollback
        vte.set_scrollback_lines(settings.scrollback_lines)

        # Cursor
        shape = _CURSOR_SHAPE_MAP.get(settings.cursor_shape, Vte.CursorShape.BLOCK)
        vte.set_cursor_shape(shape)
        vte.set_cursor_blink_mode(
            Vte.CursorBlinkMode.ON if settings.cursor_blink
            else Vte.CursorBlinkMode.OFF
        )

        # Behaviour
        vte.set_audible_bell(settings.audible_bell)
        vte.set_scroll_on_output(settings.scroll_on_output)
        vte.set_scroll_on_keystroke(settings.scroll_on_keystroke)
        vte.set_allow_bold(settings.allow_bold)
        vte.set_rewrap_on_resize(settings.rewrap_on_resize)

        # Word characters (VTE ≥ 0.40)
        try:
            vte.set_word_char_exceptions(settings.word_chars)
        except AttributeError:
            logger.debug("set_word_char_exceptions not available in this VTE version")

        # Colours
        self.apply_colors(_DEFAULT_FG, _DEFAULT_BG, _DEFAULT_PALETTE)

    def apply_colors(
        self,
        fg: str,
        bg: str,
        palette: list[str],
    ) -> None:
        """Apply a colour scheme to the terminal.

        Parameters
        ----------
        fg:
            Foreground colour as a hex string (e.g. ``"#d0d0d0"``).
        bg:
            Background colour as a hex string.
        palette:
            List of 8 or 16 hex colour strings for the terminal palette.
        """
        fg_rgba = _parse_rgba(fg)
        bg_rgba = _parse_rgba(bg)
        palette_rgba = [_parse_rgba(c) for c in palette]
        self._vte.set_colors(fg_rgba, bg_rgba, palette_rgba)

    # ── Font helpers ────────────────────────────────────────────────

    def _apply_font(self) -> None:
        desc = Pango.FontDescription.from_string(
            f"{self._font_family} {self._current_font_size}"
        )
        self._vte.set_font(desc)

    def zoom_in(self) -> None:
        """Increase terminal font size by one point."""
        self._current_font_size += 1
        self._apply_font()

    def zoom_out(self) -> None:
        """Decrease terminal font size by one point (minimum 4)."""
        if self._current_font_size > 4:
            self._current_font_size -= 1
            self._apply_font()

    def zoom_reset(self) -> None:
        """Reset font size to the configured base size."""
        self._current_font_size = self._base_font_size
        self._apply_font()

    # ── Shell spawning ──────────────────────────────────────────────

    def spawn_shell(
        self,
        command: Optional[str] = None,
        working_dir: Optional[str] = None,
    ) -> None:
        """Spawn a shell (or custom command) inside the terminal.

        Parameters
        ----------
        command:
            If given, execute this command (e.g. an SSH invocation)
            instead of the user's default shell.
        working_dir:
            Working directory for the child process.  Defaults to the
            current working directory.
        """
        if command is not None:
            argv = ["/bin/sh", "-c", command]
        else:
            shell = os.environ.get("SHELL", "/bin/bash")
            argv = [shell]

        try:
            self._vte.spawn_async(
                Vte.PtyFlags.DEFAULT,
                working_dir,
                argv,
                None,  # envv – inherit
                GLib.SpawnFlags.SEARCH_PATH,
                None,  # child-setup callback
                None,  # child-setup data
                -1,    # timeout (-1 = default)
                None,  # cancellable
                self._on_spawn_ready,
            )
        except Exception:
            logger.exception("Failed to spawn child process")

    def _on_spawn_ready(self, terminal: Vte.Terminal, pid: int, *args) -> None:
        """Callback invoked when :meth:`spawn_async` completes."""
        if pid is not None and pid > 0:
            self._child_pid = pid
            logger.debug("Child process spawned with PID %d", pid)
        else:
            error = args[0] if args else None
            logger.error("spawn_async failed: %s", error)

    # ── Child process helpers ───────────────────────────────────────

    def get_pid(self) -> int:
        """Return the PID of the child process, or ``-1`` if not running."""
        return self._child_pid

    def is_alive(self) -> bool:
        """Return ``True`` if the child process is still running."""
        if self._child_pid <= 0:
            return False
        try:
            os.kill(self._child_pid, 0)
            return True
        except OSError:
            return False

    # ── Text I/O ────────────────────────────────────────────────────

    def feed_command(self, text: str) -> None:
        """Send *text* to the terminal as if it were typed."""
        self._vte.feed_child(text.encode("utf-8"))

    def get_text(self) -> str:
        """Return the full text content of the terminal (including scrollback)."""
        result = self._vte.get_text()
        # get_text() returns (text, attributes) tuple
        if isinstance(result, tuple):
            return result[0] or ""
        return result or ""

    # ── Search ──────────────────────────────────────────────────────

    def search_text(
        self,
        pattern: str,
        regex: bool = False,
        case_sensitive: bool = True,
    ) -> bool:
        """Set the search pattern for the terminal.

        Parameters
        ----------
        pattern:
            The text or regex pattern to search for.
        regex:
            When ``True`` treat *pattern* as a GLib regex.
        case_sensitive:
            Whether the search is case-sensitive.

        Returns
        -------
        bool
            ``True`` if the search was set up successfully.
        """
        try:
            flags = 0
            if not case_sensitive:
                flags |= GLib.RegexCompileFlags.CASELESS
            if not regex:
                pattern = GLib.Regex.escape_string(pattern, -1)
            gregex = GLib.Regex.new(pattern, flags, 0)
            self._vte.search_set_gregex(gregex, 0)
            self._vte.search_set_wrap_around(True)
            return True
        except GLib.Error as exc:
            logger.warning("Invalid search pattern: %s", exc.message)
            return False

    def search_next(self) -> bool:
        """Move to the next search match.  Returns ``True`` on success."""
        return self._vte.search_find_next()

    def search_previous(self) -> bool:
        """Move to the previous search match.  Returns ``True`` on success."""
        return self._vte.search_find_previous()

    def clear_search(self) -> None:
        """Clear the active search pattern."""
        self._vte.search_set_gregex(None, 0)

    # ── Clipboard ───────────────────────────────────────────────────

    def copy_text(self) -> None:
        """Copy the current selection to the clipboard."""
        self._vte.copy_clipboard_format(Vte.Format.TEXT)

    def paste_text(self) -> None:
        """Paste from the clipboard into the terminal."""
        self._vte.paste_clipboard()

    def select_all(self) -> None:
        """Select all text in the terminal."""
        self._vte.select_all()

    # ── Reset ───────────────────────────────────────────────────────

    def reset_terminal(self, hard: bool = False) -> None:
        """Perform a terminal reset.

        Parameters
        ----------
        hard:
            When ``True`` perform a hard reset (clears scrollback).
        """
        self._vte.reset(True, hard)

    # ── Title ───────────────────────────────────────────────────────

    def get_title(self) -> str:
        """Return the window title set by escape sequences."""
        return self._vte.get_window_title() or ""

    # ── Logging ─────────────────────────────────────────────────────

    def set_logging(
        self,
        enabled: bool,
        log_file_path: Optional[str] = None,
        format: str = "plain",  # noqa: A002 – shadows builtin intentionally
        timestamps: bool = False,
    ) -> None:
        """Enable or disable logging of terminal output.

        Parameters
        ----------
        enabled:
            ``True`` to start logging, ``False`` to stop.
        log_file_path:
            Destination file path.  Required when *enabled* is ``True``.
        format:
            ``"plain"`` or ``"timestamped"``.
        timestamps:
            Whether to prepend timestamps to each line.
        """
        # Disconnect any existing handler first.
        if self._log_handler_id is not None:
            self._vte.disconnect(self._log_handler_id)
            self._log_handler_id = None

        self._logging_enabled = enabled
        self._log_format = format
        self._log_timestamps = timestamps

        if enabled:
            if log_file_path is None:
                logger.error("Logging enabled but no log_file_path provided")
                self._logging_enabled = False
                return
            self._log_file_path = log_file_path
            self._log_handler_id = self._vte.connect(
                "contents-changed", self._on_contents_changed_log
            )
            logger.info("Terminal logging started → %s", log_file_path)
        else:
            self._log_file_path = None
            logger.info("Terminal logging stopped")

    def _on_contents_changed_log(self, _terminal: Vte.Terminal) -> None:
        """Write the latest terminal content to the log file."""
        if not self._logging_enabled or self._log_file_path is None:
            return

        text = self.get_text()
        if not text:
            return

        try:
            with open(self._log_file_path, "a", encoding="utf-8") as fh:
                if self._log_timestamps:
                    stamp = datetime.datetime.now(
                        tz=datetime.timezone.utc
                    ).strftime("%Y-%m-%d %H:%M:%S")
                    fh.write(f"[{stamp}] {text}\n")
                else:
                    fh.write(text + "\n")
        except OSError:
            logger.exception("Failed to write to terminal log file")

    # ── Signal handlers ─────────────────────────────────────────────

    def _on_child_exited(self, _terminal: Vte.Terminal, _status: int) -> None:
        """Handle the ``child-exited`` signal."""
        logger.info("Child process (PID %d) exited", self._child_pid)
        self._child_pid = -1

    def _on_title_changed(self, _terminal: Vte.Terminal) -> None:
        """Handle the ``window-title-changed`` signal."""
        logger.debug("Terminal title changed to: %s", self.get_title())

    # ── Context menu ────────────────────────────────────────────────

    def _on_button_press(
        self, _widget: Gtk.Widget, event: Gdk.EventButton
    ) -> bool:
        """Show a context menu on right-click."""
        if event.button != 3:
            return False

        menu = Gtk.Menu()

        items: list[tuple[Optional[str], Optional[object]]] = [
            ("Copy", lambda *_a: self.copy_text()),
            ("Paste", lambda *_a: self.paste_text()),
            ("Select All", lambda *_a: self.select_all()),
            (None, None),  # separator
            ("Clear", lambda *_a: self.reset_terminal(hard=False)),
            ("Reset", lambda *_a: self.reset_terminal(hard=True)),
            (None, None),  # separator
            ("Find\u2026", lambda *_a: self._show_find_dialog()),
            (None, None),  # separator
            ("Copy All to Clipboard", lambda *_a: self._copy_all_to_clipboard()),
        ]

        for label, callback in items:
            if label is None:
                menu.append(Gtk.SeparatorMenuItem())
            else:
                item = Gtk.MenuItem(label=label)
                item.connect("activate", callback)
                menu.append(item)

        menu.show_all()
        # Store reference to prevent garbage collection.
        self._context_menu = menu
        menu.popup(None, None, None, None, event.button, event.time)
        return True

    def _show_find_dialog(self) -> None:
        """Open a simple find dialog."""
        dialog = Gtk.Dialog(
            title="Find",
            transient_for=self.get_toplevel(),
            flags=0,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_FIND, Gtk.ResponseType.OK,
        )

        content = dialog.get_content_area()
        entry = Gtk.Entry()
        entry.set_placeholder_text("Search text…")
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
                self.search_text(
                    pattern,
                    regex=regex_check.get_active(),
                    case_sensitive=case_check.get_active(),
                )
                self.search_next()

        dialog.destroy()

    def _copy_all_to_clipboard(self) -> None:
        """Copy the entire terminal text to the clipboard."""
        text = self.get_text()
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
