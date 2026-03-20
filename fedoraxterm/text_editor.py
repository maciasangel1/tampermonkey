"""Built-in text editor window for FedoraXTerm.

Provides :class:`TextEditorDialog`, a lightweight standalone editor
window with monospace font, line numbers, find/replace, word-wrap
toggle, and optional GtkSourceView syntax highlighting.  Files can be
opened from the local filesystem or via an SFTP client (Paramiko).
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

if TYPE_CHECKING:
    import paramiko

logger = logging.getLogger(__name__)

# ── Optional GtkSourceView support ──────────────────────────────────

_HAS_SOURCEVIEW = False
try:
    gi.require_version("GtkSource", "3.0")
    from gi.repository import GtkSource  # noqa: E402

    _HAS_SOURCEVIEW = True
except (ValueError, ImportError):
    GtkSource = None  # type: ignore[assignment,misc]

# ── Constants ────────────────────────────────────────────────────────

_DEFAULT_TAB_SIZE = 4
_DEFAULT_FONT = "Monospace 11"
_SUPPORTED_ENCODINGS = [
    "UTF-8",
    "ISO-8859-1",
    "ISO-8859-15",
    "Windows-1252",
    "ASCII",
    "UTF-16",
    "UTF-32",
    "EUC-JP",
    "Shift_JIS",
    "GB2312",
    "Big5",
    "KOI8-R",
]

# ── Undo/Redo stack ─────────────────────────────────────────────────


class _UndoStack:
    """Minimal undo / redo history for a plain Gtk.TextBuffer."""

    def __init__(self, buf: Gtk.TextBuffer) -> None:
        self._buf = buf
        self._undo: list[tuple[str, int, str]] = []
        self._redo: list[tuple[str, int, str]] = []
        self._recording = True
        self._buf.connect("insert-text", self._on_insert)
        self._buf.connect("delete-range", self._on_delete)

    # -- Signals ──────────────────────────────────────────────────

    def _on_insert(
        self,
        buf: Gtk.TextBuffer,
        location: Gtk.TextIter,
        text: str,
        length: int,
    ) -> None:
        if self._recording:
            self._undo.append(("insert", location.get_offset(), text))
            self._redo.clear()

    def _on_delete(
        self,
        buf: Gtk.TextBuffer,
        start: Gtk.TextIter,
        end: Gtk.TextIter,
    ) -> None:
        if self._recording:
            text = buf.get_text(start, end, True)
            self._undo.append(("delete", start.get_offset(), text))
            self._redo.clear()

    # -- Public ───────────────────────────────────────────────────

    def undo(self) -> None:
        """Undo the last operation."""
        if not self._undo:
            return
        action, offset, text = self._undo.pop()
        self._recording = False
        try:
            if action == "insert":
                start = self._buf.get_iter_at_offset(offset)
                end = self._buf.get_iter_at_offset(offset + len(text))
                self._buf.delete(start, end)
            else:
                it = self._buf.get_iter_at_offset(offset)
                self._buf.insert(it, text)
            self._redo.append((action, offset, text))
        finally:
            self._recording = True

    def redo(self) -> None:
        """Redo the last undone operation."""
        if not self._redo:
            return
        action, offset, text = self._redo.pop()
        self._recording = False
        try:
            if action == "insert":
                it = self._buf.get_iter_at_offset(offset)
                self._buf.insert(it, text)
            else:
                start = self._buf.get_iter_at_offset(offset)
                end = self._buf.get_iter_at_offset(offset + len(text))
                self._buf.delete(start, end)
            self._undo.append((action, offset, text))
        finally:
            self._recording = True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def clear(self) -> None:
        """Clear both stacks (e.g. after loading a new file)."""
        self._undo.clear()
        self._redo.clear()


# ── Editor window ────────────────────────────────────────────────────


class TextEditorDialog(Gtk.Window):
    """Standalone text editor window.

    Features
    --------
    * Monospace :class:`Gtk.TextView` (or :class:`GtkSource.View` when
      available) with undo/redo support.
    * Menu bar (File, Edit, View) and a toolbar.
    * Find and Replace bar (Ctrl+F / Ctrl+H).
    * Line-number display, word-wrap toggle, configurable tab size.
    * Status bar showing cursor position, encoding, and file type.
    * Local and SFTP file open/save.
    * Unsaved-changes prompt on close.

    Parameters
    ----------
    parent:
        Optional parent :class:`Gtk.Window` for transient positioning.
    """

    def __init__(self, parent: Optional[Gtk.Window] = None) -> None:
        super().__init__(
            title="Text Editor",
            default_width=820,
            default_height=620,
        )
        if parent is not None:
            self.set_transient_for(parent)

        self._filepath: Optional[str] = None
        self._encoding: str = "UTF-8"
        self._modified: bool = False
        self._word_wrap: bool = False
        self._show_line_numbers: bool = True
        self._tab_size: int = _DEFAULT_TAB_SIZE

        self._build_ui()
        self._connect_signals()
        self._update_title()
        self._update_statusbar()

    # ── UI construction ──────────────────────────────────────────

    def _build_ui(self) -> None:
        """Assemble all child widgets."""
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vbox)

        # Menu bar
        vbox.pack_start(self._build_menubar(), False, False, 0)

        # Toolbar
        vbox.pack_start(self._build_toolbar(), False, False, 0)

        # Find / Replace bar (hidden by default)
        self._find_bar = self._build_find_bar()
        self._find_bar.set_no_show_all(True)
        vbox.pack_start(self._find_bar, False, False, 0)

        # Scrolled text area
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)

        if _HAS_SOURCEVIEW:
            self._buffer = GtkSource.Buffer()
            self._textview: Gtk.TextView = GtkSource.View(buffer=self._buffer)
            self._textview.set_show_line_numbers(self._show_line_numbers)
            self._textview.set_tab_width(self._tab_size)
            self._textview.set_insert_spaces_instead_of_tabs(True)
            self._textview.set_auto_indent(True)
            self._textview.set_highlight_current_line(True)
            self._undo_stack: Optional[_UndoStack] = None
        else:
            self._buffer = Gtk.TextBuffer()
            self._textview = Gtk.TextView(buffer=self._buffer)
            self._undo_stack = _UndoStack(self._buffer)

        self._textview.set_monospace(True)
        self._textview.override_font(
            Pango.FontDescription.from_string(_DEFAULT_FONT)
        )
        self._apply_tab_size()
        self._apply_word_wrap()

        scrolled.add(self._textview)
        vbox.pack_start(scrolled, True, True, 0)

        # Status bar
        self._statusbar = Gtk.Statusbar()
        self._status_ctx = self._statusbar.get_context_id("editor")
        vbox.pack_start(self._statusbar, False, False, 0)

    # -- Menu bar ─────────────────────────────────────────────────

    def _build_menubar(self) -> Gtk.MenuBar:
        """Create the menu bar with File, Edit, View menus."""
        menubar = Gtk.MenuBar()

        # ── File ─────────────────────────────────────────────────
        file_menu = Gtk.Menu()
        file_item = Gtk.MenuItem(label="File")
        file_item.set_submenu(file_menu)

        for label, cb, accel in [
            ("New", self._on_new, "<Ctrl>N"),
            ("Open…", self._on_open, "<Ctrl>O"),
            ("Save", self._on_save, "<Ctrl>S"),
            ("Save As…", self._on_save_as, "<Ctrl><Shift>S"),
            (None, None, None),
            ("Close", self._on_close_activate, "<Ctrl>W"),
        ]:
            if label is None:
                file_menu.append(Gtk.SeparatorMenuItem())
                continue
            mi = Gtk.MenuItem(label=label)
            mi.connect("activate", cb)
            file_menu.append(mi)
        menubar.append(file_item)

        # ── Edit ─────────────────────────────────────────────────
        edit_menu = Gtk.Menu()
        edit_item = Gtk.MenuItem(label="Edit")
        edit_item.set_submenu(edit_menu)

        for label, cb, accel in [
            ("Undo", self._on_undo, "<Ctrl>Z"),
            ("Redo", self._on_redo, "<Ctrl><Shift>Z"),
            (None, None, None),
            ("Cut", self._on_cut, "<Ctrl>X"),
            ("Copy", self._on_copy, "<Ctrl>C"),
            ("Paste", self._on_paste, "<Ctrl>V"),
            ("Select All", self._on_select_all, "<Ctrl>A"),
            (None, None, None),
            ("Find…", self._on_show_find, "<Ctrl>F"),
            ("Replace…", self._on_show_replace, "<Ctrl>H"),
        ]:
            if label is None:
                edit_menu.append(Gtk.SeparatorMenuItem())
                continue
            mi = Gtk.MenuItem(label=label)
            mi.connect("activate", cb)
            edit_menu.append(mi)
        menubar.append(edit_item)

        # ── View ─────────────────────────────────────────────────
        view_menu = Gtk.Menu()
        view_item = Gtk.MenuItem(label="View")
        view_item.set_submenu(view_menu)

        self._wrap_check = Gtk.CheckMenuItem(label="Word Wrap")
        self._wrap_check.set_active(self._word_wrap)
        self._wrap_check.connect("toggled", self._on_toggle_wrap)
        view_menu.append(self._wrap_check)

        self._ln_check = Gtk.CheckMenuItem(label="Line Numbers")
        self._ln_check.set_active(self._show_line_numbers)
        self._ln_check.connect("toggled", self._on_toggle_line_numbers)
        view_menu.append(self._ln_check)

        view_menu.append(Gtk.SeparatorMenuItem())

        font_item = Gtk.MenuItem(label="Font Size")
        font_sub = Gtk.Menu()
        for label, cb in [
            ("Increase", self._on_font_increase),
            ("Decrease", self._on_font_decrease),
            ("Reset", self._on_font_reset),
        ]:
            mi = Gtk.MenuItem(label=label)
            mi.connect("activate", cb)
            font_sub.append(mi)
        font_item.set_submenu(font_sub)
        view_menu.append(font_item)

        menubar.append(view_item)
        return menubar

    # -- Toolbar ──────────────────────────────────────────────────

    def _build_toolbar(self) -> Gtk.Toolbar:
        """Create the main toolbar."""
        toolbar = Gtk.Toolbar()
        toolbar.set_style(Gtk.ToolbarStyle.ICONS)

        for stock, tooltip, cb in [
            ("document-new", "New", self._on_new),
            ("document-open", "Open", self._on_open),
            ("document-save", "Save", self._on_save),
            ("edit-find", "Find", self._on_show_find),
        ]:
            btn = Gtk.ToolButton()
            btn.set_icon_name(stock)
            btn.set_tooltip_text(tooltip)
            btn.connect("clicked", cb)
            toolbar.insert(btn, -1)

        toolbar.insert(Gtk.SeparatorToolItem(), -1)

        self._wrap_tool = Gtk.ToggleToolButton()
        self._wrap_tool.set_icon_name("format-justify-fill")
        self._wrap_tool.set_tooltip_text("Word Wrap")
        self._wrap_tool.set_active(self._word_wrap)
        self._wrap_tool.connect("toggled", self._on_toggle_wrap_tool)
        toolbar.insert(self._wrap_tool, -1)

        return toolbar

    # -- Find / Replace bar ───────────────────────────────────────

    def _build_find_bar(self) -> Gtk.Box:
        """Create the find / replace bar."""
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        outer.set_margin_start(6)
        outer.set_margin_end(6)
        outer.set_margin_top(2)
        outer.set_margin_bottom(2)

        # Find row
        find_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        find_row.pack_start(Gtk.Label(label="Find:"), False, False, 0)
        self._find_entry = Gtk.Entry()
        self._find_entry.set_hexpand(True)
        self._find_entry.connect("activate", lambda *_a: self._do_find_next())
        find_row.pack_start(self._find_entry, True, True, 0)

        next_btn = Gtk.Button(label="Next")
        next_btn.connect("clicked", lambda *_a: self._do_find_next())
        find_row.pack_start(next_btn, False, False, 0)

        prev_btn = Gtk.Button(label="Previous")
        prev_btn.connect("clicked", lambda *_a: self._do_find_prev())
        find_row.pack_start(prev_btn, False, False, 0)

        close_btn = Gtk.Button()
        close_btn.set_image(
            Gtk.Image.new_from_icon_name("window-close", Gtk.IconSize.MENU)
        )
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        close_btn.connect("clicked", lambda *_a: self._hide_find_bar())
        find_row.pack_end(close_btn, False, False, 0)

        outer.pack_start(find_row, False, False, 0)

        # Replace row (toggled)
        self._replace_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=4,
        )
        self._replace_row.pack_start(
            Gtk.Label(label="Replace:"), False, False, 0,
        )
        self._replace_entry = Gtk.Entry()
        self._replace_entry.set_hexpand(True)
        self._replace_row.pack_start(self._replace_entry, True, True, 0)

        replace_btn = Gtk.Button(label="Replace")
        replace_btn.connect("clicked", lambda *_a: self._do_replace())
        self._replace_row.pack_start(replace_btn, False, False, 0)

        replace_all_btn = Gtk.Button(label="Replace All")
        replace_all_btn.connect("clicked", lambda *_a: self._do_replace_all())
        self._replace_row.pack_start(replace_all_btn, False, False, 0)

        self._replace_row.set_no_show_all(True)
        outer.pack_start(self._replace_row, False, False, 0)

        return outer

    # ── Signal wiring ────────────────────────────────────────────

    def _connect_signals(self) -> None:
        """Wire up window and buffer signals."""
        self.connect("delete-event", self._on_delete_event)
        self.connect("key-press-event", self._on_key_press)
        self._buffer.connect("changed", self._on_buffer_changed)
        self._buffer.connect("notify::cursor-position", self._on_cursor_moved)

    # ── Public API ───────────────────────────────────────────────

    def open_file(self, filepath: str) -> None:
        """Open a local file in the editor.

        Parameters
        ----------
        filepath:
            Absolute or relative path to the file.
        """
        try:
            with open(filepath, "r", encoding=self._encoding) as fh:
                text = fh.read()
        except UnicodeDecodeError:
            with open(filepath, "r", encoding="latin-1") as fh:
                text = fh.read()
            self._encoding = "ISO-8859-1"
        self._buffer.set_text(text)
        self._filepath = os.path.abspath(filepath)
        self._modified = False
        self._apply_language()
        if self._undo_stack is not None:
            self._undo_stack.clear()
        self._update_title()
        self._update_statusbar()
        logger.info("Opened file: %s", self._filepath)

    def open_remote_file(
        self,
        sftp_client: "paramiko.SFTPClient",
        remote_path: str,
    ) -> None:
        """Open a remote file via an SFTP client.

        Parameters
        ----------
        sftp_client:
            An open :class:`paramiko.SFTPClient` instance.
        remote_path:
            The remote file path.
        """
        with sftp_client.open(remote_path, "r") as rfh:
            raw: bytes = rfh.read()
        try:
            text = raw.decode(self._encoding)
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
            self._encoding = "ISO-8859-1"
        self._buffer.set_text(text)
        self._filepath = remote_path
        self._modified = False
        if self._undo_stack is not None:
            self._undo_stack.clear()
        self._update_title()
        self._update_statusbar()
        logger.info("Opened remote file: %s", remote_path)

    def save_file(self, filepath: Optional[str] = None) -> None:
        """Save the editor content to a local file.

        Parameters
        ----------
        filepath:
            Destination path.  Falls back to the path used by the last
            :meth:`open_file` call.

        Raises
        ------
        ValueError
            If no *filepath* was supplied and no file has been opened.
        """
        path = filepath or self._filepath
        if path is None:
            raise ValueError("No filepath specified and no file is open.")
        with open(path, "w", encoding=self._encoding) as fh:
            fh.write(self.get_text())
        self._filepath = os.path.abspath(path)
        self._modified = False
        self._update_title()
        self._update_statusbar()
        logger.info("Saved file: %s", self._filepath)

    def save_remote_file(
        self,
        sftp_client: "paramiko.SFTPClient",
        remote_path: str,
    ) -> None:
        """Save the editor content to a remote file via SFTP.

        Parameters
        ----------
        sftp_client:
            An open :class:`paramiko.SFTPClient` instance.
        remote_path:
            The remote file path.
        """
        data = self.get_text().encode(self._encoding)
        with sftp_client.open(remote_path, "w") as rfh:
            rfh.write(data)
        self._filepath = remote_path
        self._modified = False
        self._update_title()
        self._update_statusbar()
        logger.info("Saved remote file: %s", remote_path)

    def get_text(self) -> str:
        """Return all text in the editor buffer.

        Returns
        -------
        str
            The full editor contents.
        """
        start = self._buffer.get_start_iter()
        end = self._buffer.get_end_iter()
        return self._buffer.get_text(start, end, True)

    def set_text(self, text: str) -> None:
        """Replace all editor content.

        Parameters
        ----------
        text:
            New content for the buffer.
        """
        self._buffer.set_text(text)
        self._modified = True
        self._update_title()

    def find_text(self, pattern: str) -> bool:
        """Search forward for *pattern* from the current cursor.

        Parameters
        ----------
        pattern:
            Plain text to search for.

        Returns
        -------
        bool
            ``True`` if a match was found and selected.
        """
        self._find_entry.set_text(pattern)
        return self._do_find_next()

    def replace_text(self, pattern: str, replacement: str) -> int:
        """Replace all occurrences of *pattern* with *replacement*.

        Parameters
        ----------
        pattern:
            Text to find.
        replacement:
            Text to substitute.

        Returns
        -------
        int
            Number of replacements made.
        """
        self._find_entry.set_text(pattern)
        self._replace_entry.set_text(replacement)
        return self._do_replace_all()

    # ── Menu / toolbar callbacks ─────────────────────────────────

    def _on_new(self, *_args: object) -> None:
        if not self._confirm_discard():
            return
        self._buffer.set_text("")
        self._filepath = None
        self._modified = False
        if self._undo_stack is not None:
            self._undo_stack.clear()
        self._update_title()
        self._update_statusbar()

    def _on_open(self, *_args: object) -> None:
        if not self._confirm_discard():
            return
        dialog = Gtk.FileChooserDialog(
            title="Open File",
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK,
        )
        if dialog.run() == Gtk.ResponseType.OK:
            self.open_file(dialog.get_filename())
        dialog.destroy()

    def _on_save(self, *_args: object) -> None:
        if self._filepath is None:
            self._on_save_as()
            return
        self.save_file()

    def _on_save_as(self, *_args: object) -> None:
        dialog = Gtk.FileChooserDialog(
            title="Save File As",
            parent=self,
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE, Gtk.ResponseType.OK,
        )
        dialog.set_do_overwrite_confirmation(True)
        if self._filepath:
            dialog.set_current_name(os.path.basename(self._filepath))
        if dialog.run() == Gtk.ResponseType.OK:
            self.save_file(dialog.get_filename())
        dialog.destroy()

    def _on_close_activate(self, *_args: object) -> None:
        self.close()

    def _on_undo(self, *_args: object) -> None:
        if _HAS_SOURCEVIEW and hasattr(self._buffer, "undo"):
            self._buffer.undo()
        elif self._undo_stack is not None:
            self._undo_stack.undo()

    def _on_redo(self, *_args: object) -> None:
        if _HAS_SOURCEVIEW and hasattr(self._buffer, "redo"):
            self._buffer.redo()
        elif self._undo_stack is not None:
            self._undo_stack.redo()

    def _on_cut(self, *_args: object) -> None:
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self._buffer.cut_clipboard(clipboard, self._textview.get_editable())

    def _on_copy(self, *_args: object) -> None:
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self._buffer.copy_clipboard(clipboard)

    def _on_paste(self, *_args: object) -> None:
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self._buffer.paste_clipboard(
            clipboard, None, self._textview.get_editable(),
        )

    def _on_select_all(self, *_args: object) -> None:
        start = self._buffer.get_start_iter()
        end = self._buffer.get_end_iter()
        self._buffer.select_range(start, end)

    def _on_show_find(self, *_args: object) -> None:
        self._replace_row.hide()
        self._find_bar.show_all()
        self._find_entry.grab_focus()

    def _on_show_replace(self, *_args: object) -> None:
        self._find_bar.show_all()
        self._replace_row.show_all()
        self._find_entry.grab_focus()

    def _on_toggle_wrap(self, item: Gtk.CheckMenuItem) -> None:
        self._word_wrap = item.get_active()
        self._wrap_tool.set_active(self._word_wrap)
        self._apply_word_wrap()

    def _on_toggle_wrap_tool(self, tool: Gtk.ToggleToolButton) -> None:
        self._word_wrap = tool.get_active()
        self._wrap_check.set_active(self._word_wrap)
        self._apply_word_wrap()

    def _on_toggle_line_numbers(self, item: Gtk.CheckMenuItem) -> None:
        self._show_line_numbers = item.get_active()
        if _HAS_SOURCEVIEW:
            self._textview.set_show_line_numbers(self._show_line_numbers)

    def _on_font_increase(self, *_args: object) -> None:
        self._change_font_size(1)

    def _on_font_decrease(self, *_args: object) -> None:
        self._change_font_size(-1)

    def _on_font_reset(self, *_args: object) -> None:
        self._textview.override_font(
            Pango.FontDescription.from_string(_DEFAULT_FONT)
        )

    # ── Key-press handler ────────────────────────────────────────

    def _on_key_press(self, _widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        """Handle global keyboard shortcuts.

        Returns
        -------
        bool
            ``True`` if the event was consumed.
        """
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        shift = event.state & Gdk.ModifierType.SHIFT_MASK

        if ctrl and event.keyval == Gdk.KEY_f:
            self._on_show_find()
            return True
        if ctrl and event.keyval == Gdk.KEY_h:
            self._on_show_replace()
            return True
        if ctrl and event.keyval == Gdk.KEY_z:
            if shift:
                self._on_redo()
            else:
                self._on_undo()
            return True
        if ctrl and event.keyval == Gdk.KEY_s:
            if shift:
                self._on_save_as()
            else:
                self._on_save()
            return True
        if ctrl and event.keyval == Gdk.KEY_n:
            self._on_new()
            return True
        if ctrl and event.keyval == Gdk.KEY_o:
            self._on_open()
            return True
        if ctrl and event.keyval == Gdk.KEY_w:
            self.close()
            return True
        if event.keyval == Gdk.KEY_Escape:
            self._hide_find_bar()
            return True
        return False

    # ── Buffer / cursor callbacks ────────────────────────────────

    def _on_buffer_changed(self, _buf: Gtk.TextBuffer) -> None:
        self._modified = True
        self._update_title()

    def _on_cursor_moved(self, *_args: object) -> None:
        self._update_statusbar()

    # ── Window close ─────────────────────────────────────────────

    def _on_delete_event(
        self, _window: Gtk.Window, _event: Gdk.Event,
    ) -> bool:
        """Intercept window close to prompt for unsaved changes.

        Returns
        -------
        bool
            ``True`` to prevent the close.
        """
        return not self._confirm_discard()

    # ── Find / replace helpers ───────────────────────────────────

    def _do_find_next(self) -> bool:
        """Search forward from the cursor.

        Returns
        -------
        bool
            ``True`` if a match was found.
        """
        pattern = self._find_entry.get_text()
        if not pattern:
            return False
        cursor_mark = self._buffer.get_insert()
        start = self._buffer.get_iter_at_mark(cursor_mark)
        found = start.forward_search(
            pattern, Gtk.TextSearchFlags.CASE_INSENSITIVE, None,
        )
        if found is None:
            # Wrap around
            found = self._buffer.get_start_iter().forward_search(
                pattern, Gtk.TextSearchFlags.CASE_INSENSITIVE, None,
            )
        if found is not None:
            match_start, match_end = found
            self._buffer.select_range(match_start, match_end)
            self._textview.scroll_to_iter(match_start, 0.1, False, 0, 0)
            return True
        return False

    def _do_find_prev(self) -> bool:
        """Search backward from the cursor.

        Returns
        -------
        bool
            ``True`` if a match was found.
        """
        pattern = self._find_entry.get_text()
        if not pattern:
            return False
        cursor_mark = self._buffer.get_insert()
        end = self._buffer.get_iter_at_mark(cursor_mark)
        found = end.backward_search(
            pattern, Gtk.TextSearchFlags.CASE_INSENSITIVE, None,
        )
        if found is None:
            found = self._buffer.get_end_iter().backward_search(
                pattern, Gtk.TextSearchFlags.CASE_INSENSITIVE, None,
            )
        if found is not None:
            match_start, match_end = found
            self._buffer.select_range(match_start, match_end)
            self._textview.scroll_to_iter(match_start, 0.1, False, 0, 0)
            return True
        return False

    def _do_replace(self) -> bool:
        """Replace the current selection if it matches the find pattern.

        Returns
        -------
        bool
            ``True`` if a replacement was made.
        """
        pattern = self._find_entry.get_text()
        replacement = self._replace_entry.get_text()
        if not pattern:
            return False
        sel = self._buffer.get_selection_bounds()
        if sel:
            start, end = sel
            selected = self._buffer.get_text(start, end, True)
            if selected.lower() == pattern.lower():
                self._buffer.delete(start, end)
                self._buffer.insert(start, replacement)
                self._do_find_next()
                return True
        self._do_find_next()
        return False

    def _do_replace_all(self) -> int:
        """Replace every occurrence.

        Returns
        -------
        int
            The number of replacements made.
        """
        pattern = self._find_entry.get_text()
        replacement = self._replace_entry.get_text()
        if not pattern:
            return 0
        text = self.get_text()
        # Case-insensitive replacement
        import re
        compiled = re.compile(re.escape(pattern), re.IGNORECASE)
        new_text, count = compiled.subn(replacement, text)
        if count:
            self._buffer.set_text(new_text)
        return count

    def _hide_find_bar(self) -> None:
        """Hide the find/replace bar and return focus to the editor."""
        self._find_bar.hide()
        self._textview.grab_focus()

    # ── Internal helpers ─────────────────────────────────────────

    def _confirm_discard(self) -> bool:
        """Prompt the user when there are unsaved changes.

        Returns
        -------
        bool
            ``True`` if it is safe to proceed (discard or no changes).
        """
        if not self._modified:
            return True
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text="Save changes before closing?",
        )
        dialog.format_secondary_text(
            "Your changes will be lost if you don't save them.",
        )
        dialog.add_buttons(
            "Don't Save", Gtk.ResponseType.REJECT,
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE, Gtk.ResponseType.OK,
        )
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self._on_save()
            return True
        return response == Gtk.ResponseType.REJECT

    def _update_title(self) -> None:
        """Refresh the window title to reflect the current file."""
        name = os.path.basename(self._filepath) if self._filepath else "Untitled"
        prefix = "● " if self._modified else ""
        self.set_title(f"{prefix}{name} — Text Editor")

    def _update_statusbar(self) -> None:
        """Refresh the status bar with cursor position and metadata."""
        cursor_mark = self._buffer.get_insert()
        it = self._buffer.get_iter_at_mark(cursor_mark)
        line = it.get_line() + 1
        col = it.get_line_offset() + 1
        ftype = self._guess_filetype()
        msg = f"Ln {line}, Col {col}    {self._encoding}    {ftype}"
        self._statusbar.pop(self._status_ctx)
        self._statusbar.push(self._status_ctx, msg)

    def _guess_filetype(self) -> str:
        """Return a short file-type label based on the file extension.

        Returns
        -------
        str
            Human-readable file-type name (e.g. ``"Python"``, ``"Plain Text"``).
        """
        if not self._filepath:
            return "Plain Text"
        ext = os.path.splitext(self._filepath)[1].lower()
        mapping: dict[str, str] = {
            ".py": "Python",
            ".sh": "Shell Script",
            ".bash": "Bash Script",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".json": "JSON",
            ".yaml": "YAML",
            ".yml": "YAML",
            ".xml": "XML",
            ".html": "HTML",
            ".css": "CSS",
            ".c": "C",
            ".cpp": "C++",
            ".h": "C/C++ Header",
            ".go": "Go",
            ".rs": "Rust",
            ".rb": "Ruby",
            ".java": "Java",
            ".md": "Markdown",
            ".txt": "Plain Text",
            ".conf": "Config",
            ".ini": "INI",
            ".toml": "TOML",
            ".cfg": "Config",
            ".log": "Log",
            ".sql": "SQL",
        }
        return mapping.get(ext, "Plain Text")

    def _apply_word_wrap(self) -> None:
        """Apply the current word-wrap setting to the text view."""
        if self._word_wrap:
            self._textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        else:
            self._textview.set_wrap_mode(Gtk.WrapMode.NONE)

    def _apply_tab_size(self) -> None:
        """Configure the tab-stop distance on the text view."""
        if _HAS_SOURCEVIEW:
            self._textview.set_tab_width(self._tab_size)
        else:
            font_desc = self._textview.get_style_context().get_font(
                Gtk.StateFlags.NORMAL,
            )
            tab_array = Pango.TabArray.new(1, True)
            # Approximate width: tab_size × average character width
            width = self._tab_size * (font_desc.get_size() // Pango.SCALE)
            tab_array.set_tab(0, Pango.TabAlign.LEFT, width)
            self._textview.set_tabs(tab_array)

    def _apply_language(self) -> None:
        """Set GtkSourceView language highlighting if available."""
        if not _HAS_SOURCEVIEW or not self._filepath:
            return
        manager = GtkSource.LanguageManager.get_default()
        language = manager.guess_language(self._filepath, None)
        if language is not None:
            self._buffer.set_language(language)
            self._buffer.set_highlight_syntax(True)

    def _change_font_size(self, delta: int) -> None:
        """Adjust the editor font size by *delta* points.

        Parameters
        ----------
        delta:
            Number of points to add (positive) or subtract (negative).
        """
        ctx = self._textview.get_style_context()
        current = ctx.get_font(Gtk.StateFlags.NORMAL)
        size = current.get_size() // Pango.SCALE + delta
        size = max(6, min(size, 72))
        current.set_size(size * Pango.SCALE)
        self._textview.override_font(current)
