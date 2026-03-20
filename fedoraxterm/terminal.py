"""VTE-based terminal widget for FedoraXTerm."""

import os
import shlex

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gtk, Vte, GLib, Gdk, Pango


class TerminalWidget(Gtk.Box):
    """A terminal emulator widget backed by the VTE library.

    Supports local shells and remote SSH sessions.
    """

    def __init__(self, settings=None, ssh_command=None):
        """Initialise the terminal.

        Args:
            settings: An ``AppSettings`` instance for font / colour prefs.
            ssh_command: If given, run this SSH command instead of a local shell.
        """
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        self.vte = Vte.Terminal()
        self._child_pid = -1
        self._ssh_command = ssh_command

        # Apply visual settings ------------------------------------------------
        if settings:
            self._apply_settings(settings)
        else:
            self._apply_defaults()

        self.vte.set_scroll_on_output(True)
        self.vte.set_scroll_on_keystroke(True)

        # Scrollbar
        scrollbar = Gtk.Scrollbar.new(
            Gtk.Orientation.VERTICAL, self.vte.get_vadjustment()
        )

        term_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        term_box.pack_start(self.vte, True, True, 0)
        term_box.pack_start(scrollbar, False, False, 0)
        self.pack_start(term_box, True, True, 0)

        # Connect signals
        self.vte.connect("child-exited", self._on_child_exited)
        self.vte.connect("button-press-event", self._on_button_press)

        # Spawn process
        self._spawn()

    # -- Public API ---------------------------------------------------------

    def feed_command(self, command: str):
        """Send a command string to the terminal."""
        self.vte.feed_child((command + "\n").encode("utf-8"))

    def copy_clipboard(self):
        """Copy selected text to clipboard."""
        self.vte.copy_clipboard_format(Vte.Format.TEXT)

    def paste_clipboard(self):
        """Paste text from the clipboard."""
        self.vte.paste_clipboard()

    def get_title(self) -> str:
        """Return the terminal's current title."""
        return self.vte.get_window_title() or "Terminal"

    def has_selection(self) -> bool:
        """Return True if the terminal has selected text."""
        return self.vte.get_has_selection()

    # -- Internal helpers ---------------------------------------------------

    def _on_button_press(self, widget, event):
        """Handle right-click on the terminal.

        Smart copy/paste behaviour (like SecureCRT / PuTTY):
        * If text is selected **and** the clipboard is empty → auto-copy
          the selection to the clipboard.
        * If the clipboard already has text → auto-paste it into the
          terminal.
        * In either case, holding Shift with the right-click opens the
          full context menu instead of the smart action.
        """
        if event.button != 3:
            return False

        # Shift+Right-click always opens the context menu
        state = event.state & Gtk.accelerator_get_default_mod_mask()
        if state & Gdk.ModifierType.SHIFT_MASK:
            return self._show_context_menu(event)

        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        has_clip_text = clipboard.wait_is_text_available()

        if has_clip_text:
            # Clipboard has content → paste
            self.paste_clipboard()
            return True

        if self.has_selection():
            # Selection exists and clipboard is empty → copy
            self.copy_clipboard()
            return True

        # Nothing selected and clipboard is empty → show context menu
        return self._show_context_menu(event)

    def _show_context_menu(self, event):
        """Build and display the terminal right-click context menu."""
        menu = Gtk.Menu()

        # Copy — only sensitive when text is selected
        copy_item = Gtk.MenuItem(label="Copy")
        copy_item.connect("activate", lambda _i: self.copy_clipboard())
        copy_item.set_sensitive(self.has_selection())
        menu.append(copy_item)

        # Paste — only sensitive when the clipboard has text
        paste_item = Gtk.MenuItem(label="Paste")
        paste_item.connect("activate", lambda _i: self.paste_clipboard())
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        paste_item.set_sensitive(clipboard.wait_is_text_available())
        menu.append(paste_item)

        menu.append(Gtk.SeparatorMenuItem())

        # Select All
        select_all_item = Gtk.MenuItem(label="Select All")
        select_all_item.connect("activate", lambda _i: self.vte.select_all())
        menu.append(select_all_item)

        menu.show_all()
        # Keep a reference to prevent GC during popup
        self._context_menu = menu
        menu.popup(None, None, None, None, event.button, event.time)
        return True

    def _apply_defaults(self):
        """Apply sensible default colours and font."""
        fg = Gdk.RGBA()
        fg.parse("#cdd6f4")
        bg = Gdk.RGBA()
        bg.parse("#1e1e2e")

        palette = []
        hex_palette = [
            "#45475a", "#f38ba8", "#a6e3a1", "#f9e2af",
            "#89b4fa", "#f5c2e7", "#94e2d5", "#bac2de",
            "#585b70", "#f38ba8", "#a6e3a1", "#f9e2af",
            "#89b4fa", "#f5c2e7", "#94e2d5", "#a6adc8",
        ]
        for h in hex_palette:
            c = Gdk.RGBA()
            c.parse(h)
            palette.append(c)

        self.vte.set_colors(fg, bg, palette)
        font_desc = Pango.FontDescription("Monospace 11")
        self.vte.set_font(font_desc)
        self.vte.set_scrollback_lines(10000)

    def _apply_settings(self, settings):
        """Apply user settings to the terminal."""
        fg = Gdk.RGBA()
        fg.parse(settings.terminal_fg_color)
        bg = Gdk.RGBA()
        bg.parse(settings.terminal_bg_color)

        palette = []
        if hasattr(settings, "_palette") and settings._palette:
            for h in settings._palette:
                c = Gdk.RGBA()
                c.parse(h)
                palette.append(c)

        self.vte.set_colors(fg, bg, palette)

        font_desc = Pango.FontDescription(
            f"{settings.font_family} {settings.font_size}"
        )
        self.vte.set_font(font_desc)
        self.vte.set_scrollback_lines(settings.scrollback_lines)

    def _spawn(self):
        """Spawn the child process (local shell or SSH).

        Defers the actual spawn until the widget is realized so the VTE
        terminal has a valid GDK window, avoiding potential segfaults in
        older VTE/PyGObject combinations.
        """
        if self._ssh_command:
            self._spawn_argv = shlex.split(self._ssh_command)
        else:
            shell = os.environ.get("SHELL", "/bin/bash")
            self._spawn_argv = [shell]

        if self.vte.get_realized():
            self._do_spawn()
        else:
            self.vte.connect("realize", lambda _w: self._do_spawn())

    def _do_spawn(self):
        """Actually fork the child process inside the VTE terminal."""
        try:
            self.vte.spawn_async(
                Vte.PtyFlags.DEFAULT,
                os.environ.get("HOME"),
                self._spawn_argv,
                None,  # environment — inherit
                GLib.SpawnFlags.SEARCH_PATH,
                None,  # child setup
                None,  # child setup data
                -1,  # timeout
                None,  # cancellable
                self._on_spawn_complete,
            )
        except Exception as exc:
            self.vte.feed(
                f"\r\nFailed to spawn process: {exc}\r\n".encode()
            )

    def _on_spawn_complete(self, terminal, pid, *args):
        """Handle spawn completion.

        Accepts ``*args`` so it works regardless of whether the VTE
        binding passes ``(terminal, pid, error)`` or
        ``(terminal, pid, error, user_data)``.
        """
        error = args[0] if args else None
        if error:
            self.vte.feed(f"\r\nError spawning process: {error}\r\n".encode())
        else:
            self._child_pid = pid

    def _on_child_exited(self, _terminal, _status):
        """Handle the child process exiting."""
        self.vte.feed(b"\r\n[Process exited]\r\n")
