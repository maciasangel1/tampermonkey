"""Local file browser widget for FedoraXTerm.

Shows files and directories in the current working directory of the active
terminal.  Supports navigation, double-click to descend into directories,
and a parent-directory button.
"""

import os
import stat

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango


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
            if name.startswith("."):
                continue  # skip hidden files by default
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
