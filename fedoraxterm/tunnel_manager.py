"""SSH tunnel / port-forwarding manager for FedoraXTerm.

Allows users to define, start, and stop SSH tunnels (local and remote
forwarding) through a graphical dialog.
"""

import os
import signal
import subprocess
import shlex
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class SSHTunnel:
    """Describes a single SSH tunnel definition."""

    name: str
    tunnel_type: str  # "local" (-L) or "remote" (-R)
    local_port: int = 0
    remote_host: str = "127.0.0.1"
    remote_port: int = 0
    ssh_host: str = ""
    ssh_port: int = 22
    ssh_user: str = ""
    private_key_path: str = ""

    def build_command(self) -> list[str]:
        """Return the ``ssh`` argv list for this tunnel."""
        cmd = ["ssh", "-N"]

        if self.ssh_port != 22:
            cmd.extend(["-p", str(self.ssh_port)])

        if self.private_key_path:
            cmd.extend(["-i", self.private_key_path])

        flag = "-L" if self.tunnel_type == "local" else "-R"
        fwd = f"{self.local_port}:{self.remote_host}:{self.remote_port}"
        cmd.extend([flag, fwd])

        dest = f"{self.ssh_user}@{self.ssh_host}" if self.ssh_user else self.ssh_host
        cmd.append(dest)
        return cmd

    def display_label(self) -> str:
        """Human-readable summary of the tunnel."""
        direction = "→" if self.tunnel_type == "local" else "←"
        return (
            f"{self.name}: "
            f"localhost:{self.local_port} {direction} "
            f"{self.remote_host}:{self.remote_port} "
            f"via {self.ssh_host}"
        )


class TunnelManager:
    """Manages running SSH tunnel sub-processes."""

    def __init__(self):
        self.tunnels: list[SSHTunnel] = []
        self._processes: dict[str, subprocess.Popen] = {}

    def add(self, tunnel: SSHTunnel):
        self.tunnels.append(tunnel)

    def remove(self, name: str):
        self.stop(name)
        self.tunnels = [t for t in self.tunnels if t.name != name]

    def start(self, name: str) -> Optional[str]:
        """Start a tunnel. Returns an error string or *None* on success."""
        tunnel = next((t for t in self.tunnels if t.name == name), None)
        if tunnel is None:
            return f"Tunnel '{name}' not found."
        if name in self._processes:
            return f"Tunnel '{name}' is already running."
        try:
            proc = subprocess.Popen(
                tunnel.build_command(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self._processes[name] = proc
            return None
        except Exception as exc:
            return str(exc)

    def stop(self, name: str):
        """Stop a running tunnel."""
        proc = self._processes.pop(name, None)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    def is_running(self, name: str) -> bool:
        proc = self._processes.get(name)
        return proc is not None and proc.poll() is None

    def stop_all(self):
        for name in list(self._processes):
            self.stop(name)


# ---------------------------------------------------------------------------
# GTK Dialogs — created via factory functions to avoid top-level GTK imports
# ---------------------------------------------------------------------------


def create_tunnel_dialog(parent=None, manager=None):
    """Create and return a TunnelDialog instance.

    GTK is imported lazily so that the pure-logic classes above remain
    usable without a display server.
    """
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib

    class _AddTunnelDialog(Gtk.Dialog):
        """Dialog to add a new SSH tunnel."""

        def __init__(self, parent_dlg):
            super().__init__(title="Add SSH Tunnel", transient_for=parent_dlg, modal=True)
            self.add_button("_Cancel", Gtk.ResponseType.CANCEL)
            self.add_button("_OK", Gtk.ResponseType.OK)

            grid = Gtk.Grid(column_spacing=8, row_spacing=8)
            grid.set_margin_start(12)
            grid.set_margin_end(12)
            grid.set_margin_top(12)
            grid.set_margin_bottom(12)

            row = 0

            def add_field(label_text, widget):
                nonlocal row
                lbl = Gtk.Label(label=label_text)
                lbl.set_xalign(1)
                grid.attach(lbl, 0, row, 1, 1)
                widget.set_hexpand(True)
                grid.attach(widget, 1, row, 1, 1)
                row += 1
                return widget

            self._name = add_field("Name:", Gtk.Entry())
            self._type = Gtk.ComboBoxText()
            self._type.append("local", "Local (-L)")
            self._type.append("remote", "Remote (-R)")
            self._type.set_active_id("local")
            add_field("Type:", self._type)
            self._local_port = add_field(
                "Local Port:", Gtk.SpinButton.new_with_range(1, 65535, 1)
            )
            self._remote_host = add_field("Remote Host:", Gtk.Entry())
            self._remote_host.set_text("127.0.0.1")
            self._remote_port = add_field(
                "Remote Port:", Gtk.SpinButton.new_with_range(1, 65535, 1)
            )
            self._ssh_host = add_field("SSH Host:", Gtk.Entry())
            self._ssh_port = add_field(
                "SSH Port:", Gtk.SpinButton.new_with_range(1, 65535, 1)
            )
            self._ssh_port.set_value(22)
            self._ssh_user = add_field("SSH User:", Gtk.Entry())

            self.get_content_area().add(grid)
            self.show_all()

        def get_tunnel(self):
            name = self._name.get_text().strip()
            ssh_host = self._ssh_host.get_text().strip()
            if not name or not ssh_host:
                return None
            return SSHTunnel(
                name=name,
                tunnel_type=self._type.get_active_id() or "local",
                local_port=int(self._local_port.get_value()),
                remote_host=self._remote_host.get_text().strip() or "127.0.0.1",
                remote_port=int(self._remote_port.get_value()),
                ssh_host=ssh_host,
                ssh_port=int(self._ssh_port.get_value()),
                ssh_user=self._ssh_user.get_text().strip(),
            )

    class TunnelDialog(Gtk.Dialog):
        """Dialog for managing SSH tunnels."""

        COL_STATUS = 0
        COL_NAME = 1
        COL_DESC = 2

        def __init__(self, parent_win=None, mgr=None):
            super().__init__(
                title="SSH Tunnel Manager",
                transient_for=parent_win,
                modal=False,
                default_width=700,
                default_height=400,
            )
            self.add_button("_Close", Gtk.ResponseType.CLOSE)
            self.connect("response", lambda d, _r: d.destroy())

            self._manager = mgr or TunnelManager()

            content = self.get_content_area()
            content.set_spacing(6)
            content.set_margin_start(8)
            content.set_margin_end(8)
            content.set_margin_top(8)
            content.set_margin_bottom(8)

            toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            for label, cb in [
                ("Add", self._on_add),
                ("Start", self._on_start),
                ("Stop", self._on_stop),
                ("Remove", self._on_remove),
            ]:
                btn = Gtk.Button(label=label)
                btn.connect("clicked", cb)
                toolbar.pack_start(btn, False, False, 0)
            content.pack_start(toolbar, False, False, 0)

            self._store = Gtk.ListStore(str, str, str)
            self._tree = Gtk.TreeView(model=self._store)
            for idx, title in [(self.COL_STATUS, "Status"),
                               (self.COL_NAME, "Name"),
                               (self.COL_DESC, "Description")]:
                renderer = Gtk.CellRendererText()
                col = Gtk.TreeViewColumn(title, renderer, text=idx)
                col.set_expand(idx == self.COL_DESC)
                self._tree.append_column(col)

            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scroll.add(self._tree)
            content.pack_start(scroll, True, True, 0)

            self._refresh()
            self.show_all()

        def _refresh(self):
            self._store.clear()
            for t in self._manager.tunnels:
                status = "● Running" if self._manager.is_running(t.name) else "○ Stopped"
                self._store.append([status, t.name, t.display_label()])

        def _get_selected_name(self):
            sel = self._tree.get_selection()
            model, it = sel.get_selected()
            if it:
                return model.get_value(it, self.COL_NAME)
            return None

        def _on_add(self, _btn):
            dialog = _AddTunnelDialog(self)
            if dialog.run() == Gtk.ResponseType.OK:
                tunnel = dialog.get_tunnel()
                if tunnel:
                    self._manager.add(tunnel)
                    self._refresh()
            dialog.destroy()

        def _on_start(self, _btn):
            name = self._get_selected_name()
            if name:
                err = self._manager.start(name)
                if err:
                    self._show_error(err)
                self._refresh()

        def _on_stop(self, _btn):
            name = self._get_selected_name()
            if name:
                self._manager.stop(name)
                self._refresh()

        def _on_remove(self, _btn):
            name = self._get_selected_name()
            if name:
                self._manager.remove(name)
                self._refresh()

        def _show_error(self, msg):
            dlg = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text=msg,
            )
            dlg.run()
            dlg.destroy()

    return TunnelDialog(parent_win=parent, mgr=manager)
