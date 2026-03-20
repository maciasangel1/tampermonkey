"""SFTP file-browser widget for FedoraXTerm.

Provides :class:`SFTPBrowser`, a :class:`Gtk.Box` subclass that presents
a dual-pane–style remote file browser backed by :mod:`paramiko`.  All
network I/O runs on background threads; the GTK main loop is never blocked.
"""

from __future__ import annotations

import os
import stat
import threading
from datetime import datetime
from pathlib import PurePosixPath
from typing import Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, GObject, Gtk, Pango  # noqa: E402

import paramiko  # noqa: E402

from fedoraxterm.settings import SSHSession  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SIZE_UNITS = ("B", "KiB", "MiB", "GiB", "TiB")


def _human_size(nbytes: int) -> str:
    """Return a human-readable file-size string."""
    size = float(nbytes)
    for unit in _SIZE_UNITS[:-1]:
        if abs(size) < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} {_SIZE_UNITS[-1]}"


def _perm_string(mode: int) -> str:
    """Convert a numeric *mode* to ``rwxrwxrwx`` format."""
    parts: list[str] = []
    for shift in (6, 3, 0):
        m = (mode >> shift) & 0o7
        parts.append(
            ("r" if m & 4 else "-")
            + ("w" if m & 2 else "-")
            + ("x" if m & 1 else "-")
        )
    return "".join(parts)


def _icon_name_for_entry(filename: str, is_dir: bool) -> str:
    """Pick a themed icon name based on extension or directory flag."""
    if is_dir:
        return "folder"
    ext = os.path.splitext(filename)[1].lower()
    mapping = {
        ".txt": "text-x-generic",
        ".log": "text-x-generic",
        ".md": "text-x-generic",
        ".py": "text-x-script",
        ".sh": "text-x-script",
        ".bash": "text-x-script",
        ".c": "text-x-csrc",
        ".h": "text-x-chdr",
        ".cpp": "text-x-c++src",
        ".java": "text-x-java",
        ".html": "text-html",
        ".xml": "text-xml",
        ".json": "text-x-generic",
        ".yaml": "text-x-generic",
        ".yml": "text-x-generic",
        ".png": "image-x-generic",
        ".jpg": "image-x-generic",
        ".jpeg": "image-x-generic",
        ".gif": "image-x-generic",
        ".svg": "image-x-generic",
        ".pdf": "application-pdf",
        ".zip": "package-x-generic",
        ".tar": "package-x-generic",
        ".gz": "package-x-generic",
        ".bz2": "package-x-generic",
        ".xz": "package-x-generic",
        ".rpm": "package-x-generic",
        ".deb": "package-x-generic",
    }
    return mapping.get(ext, "text-x-generic")


# ---------------------------------------------------------------------------
# Column indices for the ListStore
# ---------------------------------------------------------------------------
COL_ICON = 0       # str  – icon name
COL_NAME = 1       # str  – filename
COL_SIZE = 2       # str  – human-readable size
COL_MODIFIED = 3   # str  – formatted date/time
COL_PERMS = 4      # str  – rwxrwxrwx
COL_IS_DIR = 5     # bool – True for directories (hidden, used for sorting)
COL_RAW_SIZE = 6   # int  – raw byte count (hidden, used for sorting)


# ---------------------------------------------------------------------------
# SFTPBrowser widget
# ---------------------------------------------------------------------------


class SFTPBrowser(Gtk.Box):
    """Remote file-browser widget backed by Paramiko SFTP.

    Signals
    -------
    file-downloaded(remote_path: str, local_path: str)
        Emitted when a download completes successfully.
    file-uploaded(local_path: str, remote_path: str)
        Emitted when an upload completes successfully.
    connection-error(message: str)
        Emitted when a connection or SFTP error occurs.
    """

    __gsignals__ = {
        "file-downloaded": (
            GObject.SignalFlags.RUN_LAST, None, (str, str)
        ),
        "file-uploaded": (
            GObject.SignalFlags.RUN_LAST, None, (str, str)
        ),
        "connection-error": (
            GObject.SignalFlags.RUN_LAST, None, (str,)
        ),
    }

    # ------------------------------------------------------------------ init
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_size_request(100, -1)

        self._transport: Optional[paramiko.Transport] = None
        self._sftp: Optional[paramiko.SFTPClient] = None
        self._current_path: str = "/"
        self._home_path: str = "/"
        self._lock = threading.Lock()

        self._build_path_bar()
        self._build_file_list()
        self._build_status_bar()
        self._build_context_menu()
        self._setup_dnd()

    # -------------------------------------------------------------- path bar
    def _build_path_bar(self) -> None:
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        hbox.set_margin_start(4)
        hbox.set_margin_end(4)
        hbox.set_margin_top(4)

        self._path_entry = Gtk.Entry()
        self._path_entry.set_text("/")
        self._path_entry.set_hexpand(True)
        self._path_entry.connect("activate", self._on_path_activate)
        hbox.pack_start(self._path_entry, True, True, 0)

        for icon, tooltip, cb in (
            ("go-next-symbolic", "Go", self._on_go_clicked),
            ("go-up-symbolic", "Up", self._on_up_clicked),
            ("go-home-symbolic", "Home", self._on_home_clicked),
            ("view-refresh-symbolic", "Refresh", self._on_refresh_clicked),
        ):
            btn = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
            btn.set_tooltip_text(tooltip)
            btn.connect("clicked", cb)
            hbox.pack_start(btn, False, False, 0)

        self.pack_start(hbox, False, False, 0)

    # ------------------------------------------------------------ file list
    def _build_file_list(self) -> None:
        # icon-name, name, size-str, modified-str, perms-str, is-dir, raw-size
        self._store = Gtk.ListStore(str, str, str, str, str, bool, int)

        self._tree = Gtk.TreeView(model=self._store)
        self._tree.set_headers_visible(True)
        self._tree.set_enable_search(True)
        self._tree.set_search_column(COL_NAME)
        self._tree.connect("row-activated", self._on_row_activated)
        self._tree.connect("button-press-event", self._on_button_press)

        # Icon + Name (combined via CellRendererPixbuf + CellRendererText)
        col_name = Gtk.TreeViewColumn("Name")
        cell_icon = Gtk.CellRendererPixbuf()
        col_name.pack_start(cell_icon, False)
        col_name.add_attribute(cell_icon, "icon-name", COL_ICON)

        cell_text = Gtk.CellRendererText()
        cell_text.set_property("ellipsize", Pango.EllipsizeMode.END)
        col_name.pack_start(cell_text, True)
        col_name.add_attribute(cell_text, "text", COL_NAME)
        col_name.set_expand(True)
        col_name.set_sort_column_id(COL_NAME)
        self._tree.append_column(col_name)

        # Size
        col_size = Gtk.TreeViewColumn(
            "Size", Gtk.CellRendererText(), text=COL_SIZE
        )
        col_size.set_sort_column_id(COL_RAW_SIZE)
        self._tree.append_column(col_size)

        # Modified
        col_mod = Gtk.TreeViewColumn(
            "Modified", Gtk.CellRendererText(), text=COL_MODIFIED
        )
        col_mod.set_sort_column_id(COL_MODIFIED)
        self._tree.append_column(col_mod)

        # Permissions
        col_perm = Gtk.TreeViewColumn(
            "Permissions", Gtk.CellRendererText(), text=COL_PERMS
        )
        self._tree.append_column(col_perm)

        # Default sort: directories first, then alphabetical
        self._store.set_sort_func(
            COL_NAME, self._sort_name_dirs_first, None
        )
        self._store.set_sort_column_id(COL_NAME, Gtk.SortType.ASCENDING)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(
            Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
        )
        scroll.add(self._tree)
        self.pack_start(scroll, True, True, 0)

    @staticmethod
    def _sort_name_dirs_first(
        model: Gtk.TreeModel,
        iter_a: Gtk.TreeIter,
        iter_b: Gtk.TreeIter,
        _data: object,
    ) -> int:
        dir_a = model.get_value(iter_a, COL_IS_DIR)
        dir_b = model.get_value(iter_b, COL_IS_DIR)
        if dir_a != dir_b:
            return -1 if dir_a else 1
        name_a = model.get_value(iter_a, COL_NAME).lower()
        name_b = model.get_value(iter_b, COL_NAME).lower()
        return (name_a > name_b) - (name_a < name_b)

    # ----------------------------------------------------------- status bar
    def _build_status_bar(self) -> None:
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        hbox.set_margin_start(4)
        hbox.set_margin_end(4)
        hbox.set_margin_bottom(4)

        self._spinner = Gtk.Spinner()
        hbox.pack_start(self._spinner, False, False, 0)

        self._status_label = Gtk.Label(label="Disconnected")
        self._status_label.set_xalign(0.0)
        self._status_label.set_ellipsize(Pango.EllipsizeMode.END)
        hbox.pack_start(self._status_label, True, True, 0)

        self.pack_start(hbox, False, False, 0)

    # --------------------------------------------------------- context menu
    def _build_context_menu(self) -> None:
        self._context_menu = Gtk.Menu()
        items = [
            ("Download", self._on_ctx_download),
            ("Upload…", self._on_ctx_upload),
            None,
            ("Rename…", self._on_ctx_rename),
            ("Delete", self._on_ctx_delete),
            ("New Folder…", self._on_ctx_mkdir),
            ("Chmod…", self._on_ctx_chmod),
            None,
            ("Refresh", self._on_ctx_refresh),
        ]
        for entry in items:
            if entry is None:
                self._context_menu.append(Gtk.SeparatorMenuItem())
            else:
                label, handler = entry
                mi = Gtk.MenuItem(label=label)
                mi.connect("activate", handler)
                self._context_menu.append(mi)
        self._context_menu.show_all()

    # --------------------------------------------------------------- dnd
    def _setup_dnd(self) -> None:
        # Accept drops from file managers (upload)
        self._tree.drag_dest_set(
            Gtk.DestDefaults.ALL,
            [Gtk.TargetEntry.new("text/uri-list", 0, 0)],
            Gdk.DragAction.COPY,
        )
        self._tree.connect("drag-data-received", self._on_drag_data_received)

        # Allow drags from tree (download hint – actual transfer via signal)
        self._tree.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK,
            [Gtk.TargetEntry.new("text/uri-list", 0, 0)],
            Gdk.DragAction.COPY,
        )
        self._tree.connect("drag-data-get", self._on_drag_data_get)

    # ================================================================ public
    # ------------------------------------------------------------ connect
    def connect_to_server(
        self,
        hostname: str,
        port: int = 22,
        username: str = "",
        password: Optional[str] = None,
        key_file: Optional[str] = None,
    ) -> None:
        """Open an SFTP connection in a background thread.

        Parameters
        ----------
        hostname:
            Remote host.
        port:
            SSH port (default 22).
        username:
            Login user.
        password:
            Password for password-based or key-passphrase auth.
        key_file:
            Path to a private key file (PEM).
        """
        self._set_busy(True, f"Connecting to {hostname}…")
        threading.Thread(
            target=self._do_connect,
            args=(hostname, port, username, password, key_file),
            daemon=True,
        ).start()

    def disconnect(self) -> None:
        """Close the SFTP session and underlying transport."""
        with self._lock:
            if self._sftp is not None:
                try:
                    self._sftp.close()
                except Exception:
                    pass
                self._sftp = None
            if self._transport is not None:
                try:
                    self._transport.close()
                except Exception:
                    pass
                self._transport = None
        GLib.idle_add(self._store.clear)
        GLib.idle_add(self._set_busy, False, "Disconnected")

    def navigate(self, path: str) -> None:
        """Change to *path* and refresh the listing."""
        self._set_busy(True, f"Listing {path}…")
        threading.Thread(
            target=self._do_navigate, args=(path,), daemon=True
        ).start()

    def go_up(self) -> None:
        """Navigate to the parent directory."""
        parent = str(PurePosixPath(self._current_path).parent)
        self.navigate(parent)

    def go_home(self) -> None:
        """Navigate to the user's home directory."""
        self.navigate(self._home_path)

    def refresh(self) -> None:
        """Reload the current directory listing."""
        self.navigate(self._current_path)

    def download(self, remote_path: str, local_path: str) -> None:
        """Download *remote_path* to *local_path* in the background."""
        self._set_busy(True, f"Downloading {os.path.basename(remote_path)}…")
        threading.Thread(
            target=self._do_download,
            args=(remote_path, local_path),
            daemon=True,
        ).start()

    def upload(self, local_path: str, remote_path: str) -> None:
        """Upload *local_path* to *remote_path* in the background."""
        self._set_busy(True, f"Uploading {os.path.basename(local_path)}…")
        threading.Thread(
            target=self._do_upload,
            args=(local_path, remote_path),
            daemon=True,
        ).start()

    def delete(self, remote_path: str) -> None:
        """Delete the file or directory at *remote_path*."""
        self._set_busy(True, f"Deleting {os.path.basename(remote_path)}…")
        threading.Thread(
            target=self._do_delete, args=(remote_path,), daemon=True
        ).start()

    def rename(self, old_path: str, new_path: str) -> None:
        """Rename / move *old_path* to *new_path*."""
        self._set_busy(True, "Renaming…")
        threading.Thread(
            target=self._do_rename,
            args=(old_path, new_path),
            daemon=True,
        ).start()

    def mkdir(self, path: str) -> None:
        """Create a remote directory at *path*."""
        self._set_busy(True, f"Creating {path}…")
        threading.Thread(
            target=self._do_mkdir, args=(path,), daemon=True
        ).start()

    def chmod(self, path: str, mode: int) -> None:
        """Change permissions of *path* to *mode* (e.g. ``0o755``)."""
        self._set_busy(True, "Changing permissions…")
        threading.Thread(
            target=self._do_chmod, args=(path, mode), daemon=True
        ).start()

    def get_file_info(self, path: str) -> Optional[paramiko.SFTPAttributes]:
        """Return :class:`paramiko.SFTPAttributes` for *path*, or ``None``."""
        with self._lock:
            if self._sftp is None:
                return None
            try:
                return self._sftp.stat(path)
            except Exception:
                return None

    # ======================================================= background ops
    def _do_connect(
        self,
        hostname: str,
        port: int,
        username: str,
        password: Optional[str],
        key_file: Optional[str],
    ) -> None:
        try:
            transport = paramiko.Transport((hostname, port))
            pkey: Optional[paramiko.PKey] = None
            if key_file:
                pkey = paramiko.RSAKey.from_private_key_file(
                    key_file, password=password
                )
                transport.connect(username=username, pkey=pkey)
            else:
                transport.connect(username=username, password=password or "")

            sftp = paramiko.SFTPClient.from_transport(transport)
            if sftp is None:
                raise paramiko.SSHException("Failed to open SFTP session")

            home = sftp.normalize(".")
            with self._lock:
                self._transport = transport
                self._sftp = sftp
                self._home_path = home
            GLib.idle_add(self._set_busy, False, f"Connected to {hostname}")
            self._do_navigate(home)
        except Exception as exc:
            GLib.idle_add(self.emit, "connection-error", str(exc))
            GLib.idle_add(self._set_busy, False, f"Error: {exc}")

    def _do_navigate(self, path: str) -> None:
        try:
            with self._lock:
                if self._sftp is None:
                    return
                sftp = self._sftp
            entries = sftp.listdir_attr(path)
            self._current_path = path
            rows: list[tuple[str, str, str, str, str, bool, int]] = []
            for attr in entries:
                name: str = attr.filename
                if name in (".", ".."):
                    continue
                is_dir = stat.S_ISDIR(attr.st_mode or 0)
                icon = _icon_name_for_entry(name, is_dir)
                size_str = "" if is_dir else _human_size(attr.st_size or 0)
                raw_size = 0 if is_dir else (attr.st_size or 0)
                mtime = datetime.fromtimestamp(
                    attr.st_mtime or 0
                ).strftime("%Y-%m-%d %H:%M")
                perms = _perm_string(attr.st_mode or 0)
                rows.append(
                    (icon, name, size_str, mtime, perms, is_dir, raw_size)
                )
            GLib.idle_add(self._populate_store, rows, path)
        except Exception as exc:
            GLib.idle_add(self.emit, "connection-error", str(exc))
            GLib.idle_add(self._set_busy, False, f"Error: {exc}")

    def _do_download(self, remote_path: str, local_path: str) -> None:
        try:
            with self._lock:
                if self._sftp is None:
                    return
                sftp = self._sftp
            sftp.get(remote_path, local_path)
            GLib.idle_add(self.emit, "file-downloaded", remote_path, local_path)
            GLib.idle_add(
                self._set_busy,
                False,
                f"Downloaded {os.path.basename(remote_path)}",
            )
        except Exception as exc:
            GLib.idle_add(self.emit, "connection-error", str(exc))
            GLib.idle_add(self._set_busy, False, f"Error: {exc}")

    def _do_upload(self, local_path: str, remote_path: str) -> None:
        try:
            with self._lock:
                if self._sftp is None:
                    return
                sftp = self._sftp
            sftp.put(local_path, remote_path)
            GLib.idle_add(self.emit, "file-uploaded", local_path, remote_path)
            GLib.idle_add(
                self._set_busy,
                False,
                f"Uploaded {os.path.basename(local_path)}",
            )
            self._do_navigate(self._current_path)
        except Exception as exc:
            GLib.idle_add(self.emit, "connection-error", str(exc))
            GLib.idle_add(self._set_busy, False, f"Error: {exc}")

    def _do_delete(self, remote_path: str) -> None:
        try:
            with self._lock:
                if self._sftp is None:
                    return
                sftp = self._sftp
            info = sftp.stat(remote_path)
            if stat.S_ISDIR(info.st_mode or 0):
                sftp.rmdir(remote_path)
            else:
                sftp.remove(remote_path)
            self._do_navigate(self._current_path)
        except Exception as exc:
            GLib.idle_add(self.emit, "connection-error", str(exc))
            GLib.idle_add(self._set_busy, False, f"Error: {exc}")

    def _do_rename(self, old_path: str, new_path: str) -> None:
        try:
            with self._lock:
                if self._sftp is None:
                    return
                sftp = self._sftp
            sftp.rename(old_path, new_path)
            self._do_navigate(self._current_path)
        except Exception as exc:
            GLib.idle_add(self.emit, "connection-error", str(exc))
            GLib.idle_add(self._set_busy, False, f"Error: {exc}")

    def _do_mkdir(self, path: str) -> None:
        try:
            with self._lock:
                if self._sftp is None:
                    return
                sftp = self._sftp
            sftp.mkdir(path)
            self._do_navigate(self._current_path)
        except Exception as exc:
            GLib.idle_add(self.emit, "connection-error", str(exc))
            GLib.idle_add(self._set_busy, False, f"Error: {exc}")

    def _do_chmod(self, path: str, mode: int) -> None:
        try:
            with self._lock:
                if self._sftp is None:
                    return
                sftp = self._sftp
            sftp.chmod(path, mode)
            self._do_navigate(self._current_path)
        except Exception as exc:
            GLib.idle_add(self.emit, "connection-error", str(exc))
            GLib.idle_add(self._set_busy, False, f"Error: {exc}")

    # ============================================================== UI glue
    def _populate_store(
        self,
        rows: list[tuple[str, str, str, str, str, bool, int]],
        path: str,
    ) -> bool:
        """Replace the store contents (must run on the main thread)."""
        self._store.clear()
        for row in rows:
            self._store.append(row)
        self._path_entry.set_text(path)
        self._set_busy(False, f"{len(rows)} items")
        return False  # GLib.idle_add one-shot

    def _set_busy(self, busy: bool, message: str = "") -> bool:
        if busy:
            self._spinner.start()
        else:
            self._spinner.stop()
        if message:
            self._status_label.set_text(message)
        return False  # GLib.idle_add one-shot

    # ---- selected item helpers -------------------------------------------
    def _selected_name(self) -> Optional[str]:
        sel = self._tree.get_selection()
        model, treeiter = sel.get_selected()
        if treeiter is None:
            return None
        return model.get_value(treeiter, COL_NAME)

    def _selected_is_dir(self) -> bool:
        sel = self._tree.get_selection()
        model, treeiter = sel.get_selected()
        if treeiter is None:
            return False
        return model.get_value(treeiter, COL_IS_DIR)

    def _selected_remote_path(self) -> Optional[str]:
        name = self._selected_name()
        if name is None:
            return None
        return str(PurePosixPath(self._current_path) / name)

    # ---- GTK signal handlers ---------------------------------------------
    def _on_path_activate(self, entry: Gtk.Entry) -> None:
        self.navigate(entry.get_text().strip())

    def _on_go_clicked(self, _btn: Gtk.Button) -> None:
        self.navigate(self._path_entry.get_text().strip())

    def _on_up_clicked(self, _btn: Gtk.Button) -> None:
        self.go_up()

    def _on_home_clicked(self, _btn: Gtk.Button) -> None:
        self.go_home()

    def _on_refresh_clicked(self, _btn: Gtk.Button) -> None:
        self.refresh()

    def _on_row_activated(
        self,
        tree: Gtk.TreeView,
        path: Gtk.TreePath,
        _col: Gtk.TreeViewColumn,
    ) -> None:
        treeiter = self._store.get_iter(path)
        is_dir = self._store.get_value(treeiter, COL_IS_DIR)
        name = self._store.get_value(treeiter, COL_NAME)
        if is_dir:
            self.navigate(
                str(PurePosixPath(self._current_path) / name)
            )

    def _on_button_press(
        self, tree: Gtk.TreeView, event: Gdk.EventButton
    ) -> bool:
        if event.button == 3:  # right-click
            path_info = tree.get_path_at_pos(int(event.x), int(event.y))
            if path_info is not None:
                tree.get_selection().select_path(path_info[0])
            self._context_menu.popup(
                None, None, None, None, event.button, event.time
            )
            return True
        return False

    # ---- context-menu handlers -------------------------------------------
    def _on_ctx_download(self, _mi: Gtk.MenuItem) -> None:
        remote = self._selected_remote_path()
        if remote is None:
            return
        dlg = Gtk.FileChooserDialog(
            title="Save as…",
            action=Gtk.FileChooserAction.SAVE,
        )
        dlg.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE, Gtk.ResponseType.ACCEPT,
        )
        dlg.set_current_name(self._selected_name() or "file")
        if dlg.run() == Gtk.ResponseType.ACCEPT:
            local = dlg.get_filename()
            if local:
                self.download(remote, local)
        dlg.destroy()

    def _on_ctx_upload(self, _mi: Gtk.MenuItem) -> None:
        dlg = Gtk.FileChooserDialog(
            title="Upload file…",
            action=Gtk.FileChooserAction.OPEN,
        )
        dlg.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.ACCEPT,
        )
        if dlg.run() == Gtk.ResponseType.ACCEPT:
            local = dlg.get_filename()
            if local:
                basename = os.path.basename(local)
                remote = str(
                    PurePosixPath(self._current_path) / basename
                )
                self.upload(local, remote)
        dlg.destroy()

    def _on_ctx_rename(self, _mi: Gtk.MenuItem) -> None:
        old = self._selected_remote_path()
        old_name = self._selected_name()
        if old is None or old_name is None:
            return
        dlg = Gtk.Dialog(
            title="Rename",
            flags=Gtk.DialogFlags.MODAL,
        )
        dlg.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        entry = Gtk.Entry()
        entry.set_text(old_name)
        entry.set_activates_default(True)
        dlg.get_content_area().pack_start(entry, True, True, 8)
        dlg.set_default_response(Gtk.ResponseType.OK)
        dlg.show_all()
        if dlg.run() == Gtk.ResponseType.OK:
            new_name = entry.get_text().strip()
            if new_name and new_name != old_name:
                new = str(
                    PurePosixPath(self._current_path) / new_name
                )
                self.rename(old, new)
        dlg.destroy()

    def _on_ctx_delete(self, _mi: Gtk.MenuItem) -> None:
        remote = self._selected_remote_path()
        name = self._selected_name()
        if remote is None or name is None:
            return
        dlg = Gtk.MessageDialog(
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f'Delete "{name}"?',
        )
        if dlg.run() == Gtk.ResponseType.YES:
            self.delete(remote)
        dlg.destroy()

    def _on_ctx_mkdir(self, _mi: Gtk.MenuItem) -> None:
        dlg = Gtk.Dialog(
            title="New Folder",
            flags=Gtk.DialogFlags.MODAL,
        )
        dlg.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        entry = Gtk.Entry()
        entry.set_text("new_folder")
        entry.set_activates_default(True)
        dlg.get_content_area().pack_start(entry, True, True, 8)
        dlg.set_default_response(Gtk.ResponseType.OK)
        dlg.show_all()
        if dlg.run() == Gtk.ResponseType.OK:
            name = entry.get_text().strip()
            if name:
                path = str(PurePosixPath(self._current_path) / name)
                self.mkdir(path)
        dlg.destroy()

    def _on_ctx_chmod(self, _mi: Gtk.MenuItem) -> None:
        remote = self._selected_remote_path()
        if remote is None:
            return
        dlg = Gtk.Dialog(
            title="Change Permissions",
            flags=Gtk.DialogFlags.MODAL,
        )
        dlg.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        entry = Gtk.Entry()
        entry.set_text("755")
        entry.set_activates_default(True)
        dlg.get_content_area().pack_start(entry, True, True, 8)
        dlg.set_default_response(Gtk.ResponseType.OK)
        dlg.show_all()
        if dlg.run() == Gtk.ResponseType.OK:
            text = entry.get_text().strip()
            try:
                mode = int(text, 8)
                self.chmod(remote, mode)
            except ValueError:
                pass
        dlg.destroy()

    def _on_ctx_refresh(self, _mi: Gtk.MenuItem) -> None:
        self.refresh()

    # ---- drag-and-drop ---------------------------------------------------
    def _on_drag_data_received(
        self,
        _widget: Gtk.Widget,
        _ctx: Gdk.DragContext,
        _x: int,
        _y: int,
        data: Gtk.SelectionData,
        _info: int,
        _time: int,
    ) -> None:
        uris = data.get_uris()
        if not uris:
            return
        for uri in uris:
            if uri.startswith("file://"):
                local = uri[7:]
                basename = os.path.basename(local)
                remote = str(
                    PurePosixPath(self._current_path) / basename
                )
                self.upload(local, remote)

    def _on_drag_data_get(
        self,
        _widget: Gtk.Widget,
        _ctx: Gdk.DragContext,
        data: Gtk.SelectionData,
        _info: int,
        _time: int,
    ) -> None:
        remote = self._selected_remote_path()
        if remote is not None:
            # Provide a placeholder URI so the desktop knows a path is coming
            data.set_uris([f"sftp://{remote}"])
