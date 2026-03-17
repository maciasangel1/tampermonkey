"""Network diagnostic tools for FedoraXTerm.

Provides wrappers around common networking utilities (ping, traceroute,
nslookup, port scan) and a GTK dialog for interactive use.
"""

import shlex
import socket
import subprocess
import threading
from typing import Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib


# ---------------------------------------------------------------------------
# Pure-logic helpers (no GTK dependency — easy to unit-test)
# ---------------------------------------------------------------------------

def run_ping(host: str, count: int = 4) -> str:
    """Run ``ping`` and return the output text.

    Args:
        host: Hostname or IP to ping.
        count: Number of ICMP echo requests.

    Returns:
        The standard output of the ``ping`` command.
    """
    try:
        result = subprocess.run(
            ["ping", "-c", str(count), host],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout + result.stderr
    except FileNotFoundError:
        return "Error: 'ping' command not found."
    except subprocess.TimeoutExpired:
        return "Error: ping timed out."


def run_traceroute(host: str) -> str:
    """Run ``traceroute`` and return the output text."""
    try:
        result = subprocess.run(
            ["traceroute", host],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.stdout + result.stderr
    except FileNotFoundError:
        return "Error: 'traceroute' command not found. Install with: sudo dnf install traceroute"
    except subprocess.TimeoutExpired:
        return "Error: traceroute timed out."


def run_nslookup(host: str) -> str:
    """Run ``nslookup`` and return the output text."""
    try:
        result = subprocess.run(
            ["nslookup", host],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.stdout + result.stderr
    except FileNotFoundError:
        return "Error: 'nslookup' command not found. Install with: sudo dnf install bind-utils"
    except subprocess.TimeoutExpired:
        return "Error: nslookup timed out."


def scan_port(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check whether a single TCP port is open.

    Args:
        host: Hostname or IP.
        port: TCP port number.
        timeout: Connection timeout in seconds.

    Returns:
        ``True`` if the port is open, ``False`` otherwise.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ConnectionRefusedError, TimeoutError):
        return False


def scan_ports(host: str, ports: list[int], timeout: float = 2.0) -> dict[int, bool]:
    """Scan a list of TCP ports.

    Args:
        host: Hostname or IP.
        ports: List of port numbers to scan.
        timeout: Per-port timeout.

    Returns:
        Mapping of port → open/closed.
    """
    results: dict[int, bool] = {}
    for port in ports:
        results[port] = scan_port(host, port, timeout)
    return results


COMMON_PORTS = [
    21, 22, 23, 25, 53, 80, 110, 143, 443, 445,
    993, 995, 3306, 3389, 5432, 5900, 6379, 8080, 8443, 9090,
]

# ---------------------------------------------------------------------------
# GTK Dialog
# ---------------------------------------------------------------------------


class NetworkToolsDialog(Gtk.Dialog):
    """A dialog window exposing network diagnostic tools."""

    def __init__(self, parent: Optional[Gtk.Window] = None):
        super().__init__(
            title="Network Tools",
            transient_for=parent,
            modal=False,
            default_width=650,
            default_height=520,
        )
        self.add_button("_Close", Gtk.ResponseType.CLOSE)
        self.connect("response", lambda d, _r: d.destroy())

        content = self.get_content_area()
        content.set_spacing(8)
        content.set_margin_start(8)
        content.set_margin_end(8)
        content.set_margin_top(8)
        content.set_margin_bottom(8)

        # Host entry
        host_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        host_box.pack_start(Gtk.Label(label="Host:"), False, False, 0)
        self._host_entry = Gtk.Entry()
        self._host_entry.set_hexpand(True)
        self._host_entry.set_placeholder_text("e.g. 192.168.1.1 or example.com")
        host_box.pack_start(self._host_entry, True, True, 0)
        content.pack_start(host_box, False, False, 0)

        # Tool buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for label, handler in [
            ("Ping", self._on_ping),
            ("Traceroute", self._on_traceroute),
            ("NSLookup", self._on_nslookup),
            ("Port Scan", self._on_port_scan),
        ]:
            btn = Gtk.Button(label=label)
            btn.connect("clicked", handler)
            btn_box.pack_start(btn, True, True, 0)
        content.pack_start(btn_box, False, False, 0)

        # Output area
        self._buffer = Gtk.TextBuffer()
        self._textview = Gtk.TextView(buffer=self._buffer)
        self._textview.set_editable(False)
        self._textview.set_monospace(True)
        self._textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self._textview)
        content.pack_start(scroll, True, True, 0)

        # Spinner / progress
        self._spinner = Gtk.Spinner()
        content.pack_start(self._spinner, False, False, 0)

        self.show_all()

    # -- helpers ------------------------------------------------------------

    def _get_host(self) -> str:
        return self._host_entry.get_text().strip()

    def _append_output(self, text: str):
        """Append text to the output buffer (main thread safe)."""
        end_iter = self._buffer.get_end_iter()
        self._buffer.insert(end_iter, text + "\n")

    def _run_async(self, func, *args):
        """Run *func* in a background thread and display its result."""
        host = self._get_host()
        if not host:
            self._append_output("Please enter a hostname or IP address.")
            return

        self._spinner.start()
        self._append_output(f"\n--- Running on {host} ---")

        def worker():
            result = func(host, *args)
            GLib.idle_add(self._finish_async, result)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_async(self, result: str):
        self._append_output(result)
        self._spinner.stop()

    # -- signal handlers ----------------------------------------------------

    def _on_ping(self, _btn):
        self._run_async(run_ping)

    def _on_traceroute(self, _btn):
        self._run_async(run_traceroute)

    def _on_nslookup(self, _btn):
        self._run_async(run_nslookup)

    def _on_port_scan(self, _btn):
        host = self._get_host()
        if not host:
            self._append_output("Please enter a hostname or IP address.")
            return

        self._spinner.start()
        self._append_output(f"\n--- Port scan on {host} (common ports) ---")

        def worker():
            results = scan_ports(host, COMMON_PORTS)
            lines = []
            for port, is_open in sorted(results.items()):
                state = "OPEN" if is_open else "closed"
                lines.append(f"  Port {port:>5d}: {state}")
            GLib.idle_add(self._finish_async, "\n".join(lines))

        threading.Thread(target=worker, daemon=True).start()
