"""Built-in text editor for FedoraXTerm.

Provides a simple multi-tab text editor using GtkSourceView (if available)
or a plain GtkTextView.
"""

import os
from typing import Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, GLib

# GtkSourceView is optional — fall back to plain GtkTextView
try:
    gi.require_version("GtkSource", "3.0")
    from gi.repository import GtkSource

    _HAS_SOURCEVIEW = True
except (ImportError, ValueError):
    _HAS_SOURCEVIEW = False


class EditorTab(Gtk.Box):
    """A single file-editing tab."""

    def __init__(self, filepath: Optional[str] = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.filepath = filepath
        self._modified = False

        if _HAS_SOURCEVIEW:
            self._buffer = GtkSource.Buffer()
            self._view = GtkSource.View(buffer=self._buffer)
            self._view.set_show_line_numbers(True)
            self._view.set_auto_indent(True)
            self._view.set_tab_width(4)
            self._view.set_insert_spaces_instead_of_tabs(True)
            self._view.set_highlight_current_line(True)

            lang_manager = GtkSource.LanguageManager.get_default()
            if filepath:
                lang = lang_manager.guess_language(filepath, None)
                if lang:
                    self._buffer.set_language(lang)

            style_manager = GtkSource.StyleSchemeManager.get_default()
            scheme = style_manager.get_scheme("oblivion")
            if scheme:
                self._buffer.set_style_scheme(scheme)
        else:
            self._buffer = Gtk.TextBuffer()
            self._view = Gtk.TextView(buffer=self._buffer)

        self._view.set_monospace(True)
        font = Pango.FontDescription("Monospace 11")
        self._view.override_font(font)
        self._view.set_wrap_mode(Gtk.WrapMode.NONE)

        self._buffer.connect("changed", self._on_changed)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self._view)
        self.pack_start(scroll, True, True, 0)

        if filepath and os.path.isfile(filepath):
            self._load_file(filepath)

    @property
    def modified(self) -> bool:
        return self._modified

    @property
    def title(self) -> str:
        name = os.path.basename(self.filepath) if self.filepath else "Untitled"
        return f"{'● ' if self._modified else ''}{name}"

    def _load_file(self, path: str):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            self._buffer.set_text(text)
            self._modified = False
        except OSError:
            self._buffer.set_text(f"[Could not read {path}]")

    def save(self) -> bool:
        """Save the buffer to ``self.filepath``. Returns success."""
        if not self.filepath:
            return False
        start = self._buffer.get_start_iter()
        end = self._buffer.get_end_iter()
        text = self._buffer.get_text(start, end, True)
        try:
            with open(self.filepath, "w", encoding="utf-8") as fh:
                fh.write(text)
            self._modified = False
            return True
        except OSError:
            return False

    def _on_changed(self, _buf):
        self._modified = True


class TextEditorDialog(Gtk.Window):
    """A standalone editor window with tabbed editing."""

    def __init__(self, parent=None, filepath: Optional[str] = None):
        super().__init__(title="FedoraXTerm Editor", default_width=800, default_height=600)
        if parent:
            self.set_transient_for(parent)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vbox)

        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        toolbar.set_margin_start(4)
        toolbar.set_margin_end(4)
        toolbar.set_margin_top(4)

        open_btn = Gtk.Button(label="Open")
        open_btn.connect("clicked", self._on_open)
        toolbar.pack_start(open_btn, False, False, 0)

        save_btn = Gtk.Button(label="Save")
        save_btn.connect("clicked", self._on_save)
        toolbar.pack_start(save_btn, False, False, 0)

        save_as_btn = Gtk.Button(label="Save As")
        save_as_btn.connect("clicked", self._on_save_as)
        toolbar.pack_start(save_as_btn, False, False, 0)

        new_btn = Gtk.Button(label="New")
        new_btn.connect("clicked", self._on_new)
        toolbar.pack_start(new_btn, False, False, 0)

        vbox.pack_start(toolbar, False, False, 0)

        # Notebook
        self._notebook = Gtk.Notebook()
        self._notebook.set_scrollable(True)
        vbox.pack_start(self._notebook, True, True, 0)

        if filepath:
            self._add_tab(filepath)
        else:
            self._add_tab(None)

        self.show_all()

    def _add_tab(self, filepath: Optional[str]):
        tab = EditorTab(filepath)
        label = Gtk.Label(label=tab.title)
        self._notebook.append_page(tab, label)
        self._notebook.set_tab_reorderable(tab, True)
        self._notebook.show_all()
        self._notebook.set_current_page(self._notebook.page_num(tab))

    def _current_tab(self) -> Optional[EditorTab]:
        idx = self._notebook.get_current_page()
        if idx < 0:
            return None
        return self._notebook.get_nth_page(idx)

    def _on_open(self, _btn):
        dialog = Gtk.FileChooserDialog(
            title="Open File",
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("_Open", Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            self._add_tab(dialog.get_filename())
        dialog.destroy()

    def _on_save(self, _btn):
        tab = self._current_tab()
        if tab is None:
            return
        if tab.filepath:
            tab.save()
            self._update_tab_label(tab)
        else:
            self._on_save_as(_btn)

    def _on_save_as(self, _btn):
        tab = self._current_tab()
        if tab is None:
            return
        dialog = Gtk.FileChooserDialog(
            title="Save File As",
            parent=self,
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("_Save", Gtk.ResponseType.OK)
        dialog.set_do_overwrite_confirmation(True)
        if dialog.run() == Gtk.ResponseType.OK:
            tab.filepath = dialog.get_filename()
            tab.save()
            self._update_tab_label(tab)
        dialog.destroy()

    def _on_new(self, _btn):
        self._add_tab(None)

    def _update_tab_label(self, tab: EditorTab):
        idx = self._notebook.page_num(tab)
        if idx >= 0:
            lbl = self._notebook.get_tab_label(tab)
            lbl.set_text(tab.title)
