"""SFTP file-browser panel for FedoraXTerm.

This provides a GTK TreeView that lets users browse the remote filesystem
via an SSH/SFTP connection powered by Paramiko.
"""

import os
import stat
import threading
from typing import Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk

try:
    import paramiko
except ImportError:
    paramiko = None  # Graceful degradation if paramiko is not installed


def _human_size(nbytes: int) -> str:
    """Return a human-readable file size string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"


class SFTPBrowser(Gtk.Box):
    """A panel showing a remote file listing over SFTP."""

    # TreeStore columns: icon-name, filename, size-text, is-dir, full-path
    COL_ICON = 0
    COL_NAME = 1
    COL_SIZE = 2
    COL_IS_DIR = 3
    COL_PATH = 4

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_size_request(260, -1)

        self._sftp: Optional["paramiko.SFTPClient"] = None
        self._transport: Optional["paramiko.Transport"] = None
        self._cwd = "/"

        # -- Header bar with path entry & buttons --
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        header.set_margin_start(4)
        header.set_margin_end(4)
        header.set_margin_top(4)

        self._path_entry = Gtk.Entry()
        self._path_entry.set_text("/")
        self._path_entry.set_hexpand(True)
        self._path_entry.connect("activate", self._on_path_activated)
        header.pack_start(self._path_entry, True, True, 0)

        go_btn = Gtk.Button(label="Go")
        go_btn.connect("clicked", self._on_path_activated)
        header.pack_start(go_btn, False, False, 0)

        up_btn = Gtk.Button(label="↑")
        up_btn.set_tooltip_text("Go to parent directory")
        up_btn.connect("clicked", self._on_go_up)
        header.pack_start(up_btn, False, False, 0)

        refresh_btn = Gtk.Button(label="⟳")
        refresh_btn.set_tooltip_text("Refresh")
        refresh_btn.connect("clicked", lambda _b: self._list_dir(self._cwd))
        header.pack_start(refresh_btn, False, False, 0)

        self.pack_start(header, False, False, 0)

        # -- File list (TreeView) --
        self._store = Gtk.ListStore(str, str, str, bool, str)
        self._tree = Gtk.TreeView(model=self._store)
        self._tree.set_headers_visible(True)

        renderer_icon = Gtk.CellRendererPixbuf()
        col_icon = Gtk.TreeViewColumn("", renderer_icon, icon_name=self.COL_ICON)
        col_icon.set_fixed_width(30)
        self._tree.append_column(col_icon)

        renderer_name = Gtk.CellRendererText()
        col_name = Gtk.TreeViewColumn("Name", renderer_name, text=self.COL_NAME)
        col_name.set_expand(True)
        col_name.set_sort_column_id(self.COL_NAME)
        self._tree.append_column(col_name)

        renderer_size = Gtk.CellRendererText()
        col_size = Gtk.TreeViewColumn("Size", renderer_size, text=self.COL_SIZE)
        col_size.set_fixed_width(80)
        self._tree.append_column(col_size)

        self._tree.connect("row-activated", self._on_row_activated)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self._tree)
        self.pack_start(scroll, True, True, 0)

        # -- Status bar --
        self._status = Gtk.Label(label="Not connected")
        self._status.set_xalign(0)
        self._status.set_margin_start(4)
        self._status.set_margin_bottom(4)
        self.pack_start(self._status, False, False, 0)

    # -- Public API ---------------------------------------------------------

    def connect_sftp(self, host: str, port: int, username: str,
                     password: str = "", private_key_path: str = ""):
        """Open an SFTP session in a background thread.

        Args:
            host: Remote hostname.
            port: SSH port.
            username: Remote user.
            password: Password (used when *private_key_path* is empty).
            private_key_path: Path to private key file.
        """
        if paramiko is None:
            self._set_status("paramiko not installed – SFTP unavailable")
            return

        self._set_status(f"Connecting to {host}:{port}…")
        thread = threading.Thread(
            target=self._connect_worker,
            args=(host, port, username, password, private_key_path),
            daemon=True,
        )
        thread.start()

    def disconnect(self):
        """Close the SFTP session."""
        if self._sftp:
            self._sftp.close()
            self._sftp = None
        if self._transport:
            self._transport.close()
            self._transport = None
        self._store.clear()
        self._set_status("Disconnected")

    # -- Internal helpers ---------------------------------------------------

    def _connect_worker(self, host, port, username, password, key_path):
        """Background thread: establish the SFTP connection."""
        try:
            transport = paramiko.Transport((host, port))
            if key_path and os.path.isfile(key_path):
                pkey = paramiko.RSAKey.from_private_key_file(key_path)
                transport.connect(username=username, pkey=pkey)
            else:
                transport.connect(username=username, password=password)

            sftp = paramiko.SFTPClient.from_transport(transport)
            GLib.idle_add(self._on_connected, transport, sftp)
        except Exception as exc:
            GLib.idle_add(self._set_status, f"Connection failed: {exc}")

    def _on_connected(self, transport, sftp):
        """Called on the main thread when the connection is ready."""
        self._transport = transport
        self._sftp = sftp
        self._set_status("Connected")
        self._list_dir("/")

    def _list_dir(self, path: str):
        """Populate the tree store with the contents of *path*."""
        if not self._sftp:
            return

        self._cwd = path
        self._path_entry.set_text(path)
        self._store.clear()
        self._set_status(f"Listing {path}…")

        thread = threading.Thread(
            target=self._list_dir_worker, args=(path,), daemon=True
        )
        thread.start()

    def _list_dir_worker(self, path):
        """Background: read directory entries."""
        try:
            entries = self._sftp.listdir_attr(path)
            entries.sort(key=lambda a: (not stat.S_ISDIR(a.st_mode), a.filename.lower()))
            GLib.idle_add(self._populate_store, path, entries)
        except Exception as exc:
            GLib.idle_add(self._set_status, f"Error: {exc}")

    def _populate_store(self, path, entries):
        """Populate the ListStore on the main thread."""
        self._store.clear()
        for attr in entries:
            is_dir = stat.S_ISDIR(attr.st_mode)
            icon = "folder" if is_dir else "text-x-generic"
            size = "" if is_dir else _human_size(attr.st_size)
            full = os.path.join(path, attr.filename)
            self._store.append([icon, attr.filename, size, is_dir, full])
        self._set_status(f"{path}  ({len(entries)} items)")

    def _set_status(self, text: str):
        """Update the status label."""
        self._status.set_text(text)

    # -- Signal handlers ----------------------------------------------------

    def _on_row_activated(self, _tree, treepath, _column):
        """Handle double-clicking a row."""
        it = self._store.get_iter(treepath)
        is_dir = self._store.get_value(it, self.COL_IS_DIR)
        full_path = self._store.get_value(it, self.COL_PATH)
        if is_dir:
            self._list_dir(full_path)

    def _on_path_activated(self, _widget):
        """Handle pressing Enter in the path entry."""
        self._list_dir(self._path_entry.get_text().strip())

    def _on_go_up(self, _btn):
        """Navigate to the parent directory."""
        parent = os.path.dirname(self._cwd.rstrip("/")) or "/"
        self._list_dir(parent)
