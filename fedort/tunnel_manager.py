"""SSH tunnel / port-forwarding manager for FedoRT.

Manages local, remote, and dynamic (SOCKS) SSH tunnels as background
``ssh`` processes.  Tunnels can be persisted to a JSON file and
optionally started automatically on application launch.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Fields that represent transient runtime state and must not be persisted.
_TRANSIENT_FIELDS = frozenset({"is_running", "pid"})

# ── dataclass ────────────────────────────────────────────────────


@dataclass
class Tunnel:
    """Describes a single SSH tunnel.

    Attributes
    ----------
    tunnel_type:
        One of ``"local"``, ``"remote"``, or ``"dynamic"``.
    local_host:
        Bind address on the local side (default ``127.0.0.1``).
    local_port:
        Local port to bind (or SOCKS port for dynamic tunnels).
    remote_host:
        Remote host for local/remote forwarding.
    remote_port:
        Remote port for local/remote forwarding.
    ssh_host:
        SSH server hostname.
    ssh_port:
        SSH server port.
    ssh_user:
        SSH username.
    key_file:
        Path to an SSH private key (``None`` for password / agent auth).
    name:
        Human-readable display name.
    auto_start:
        Whether to start this tunnel automatically on application launch.
    is_running:
        Runtime-only flag — ``True`` while the tunnel process is alive.
    pid:
        PID of the background ``ssh`` process, or ``None``.
    """

    tunnel_type: str = "local"
    local_host: str = "127.0.0.1"
    local_port: int = 0
    remote_host: str = ""
    remote_port: int = 0
    ssh_host: str = ""
    ssh_port: int = 22
    ssh_user: str = ""
    key_file: Optional[str] = None
    name: str = ""
    auto_start: bool = False
    # transient – not persisted
    is_running: bool = False
    pid: Optional[int] = None


# ── manager ──────────────────────────────────────────────────────


class TunnelManager:
    """Create, start, stop, and persist SSH tunnels."""

    def __init__(self) -> None:
        self.tunnels: list[Tunnel] = []
        self._lock = threading.Lock()

    # ── tunnel list manipulation ─────────────────────────────────

    def add_tunnel(self, tunnel: Tunnel) -> None:
        """Append *tunnel* to the managed list."""
        with self._lock:
            self.tunnels.append(tunnel)

    def remove_tunnel(self, tunnel: Tunnel) -> None:
        """Stop *tunnel* (if running) and remove it from the list.

        Raises
        ------
        ValueError
            If *tunnel* is not in the managed list.
        """
        self.stop_tunnel(tunnel)
        with self._lock:
            self.tunnels.remove(tunnel)

    # ── command construction ─────────────────────────────────────

    @staticmethod
    def build_tunnel_command(tunnel: Tunnel) -> list[str]:
        """Build the ``ssh`` argument list for *tunnel*.

        Returns
        -------
        list[str]
            A list suitable for :func:`subprocess.Popen`.

        Raises
        ------
        ValueError
            If ``tunnel.tunnel_type`` is not recognised.
        """
        ssh = shutil.which("ssh")
        if ssh is None:
            raise FileNotFoundError("ssh: command not found")

        cmd: list[str] = [ssh]

        # Background / no remote command
        cmd += ["-N"]

        # Keepalive
        cmd += ["-o", "ServerAliveInterval=30"]
        cmd += ["-o", "ServerAliveCountMax=3"]

        # Disable strict host-key checking for non-interactive use
        cmd += ["-o", "ExitOnForwardFailure=yes"]

        # Port
        if tunnel.ssh_port != 22:
            cmd += ["-p", str(tunnel.ssh_port)]

        # Key auth
        if tunnel.key_file:
            cmd += ["-i", tunnel.key_file]

        # Forwarding directive
        if tunnel.tunnel_type == "local":
            cmd += [
                "-L",
                f"{tunnel.local_host}:{tunnel.local_port}:"
                f"{tunnel.remote_host}:{tunnel.remote_port}",
            ]
        elif tunnel.tunnel_type == "remote":
            cmd += [
                "-R",
                f"{tunnel.remote_port}:{tunnel.local_host}:{tunnel.local_port}",
            ]
        elif tunnel.tunnel_type == "dynamic":
            cmd += ["-D", f"{tunnel.local_host}:{tunnel.local_port}"]
        else:
            raise ValueError(
                f"Unknown tunnel type: {tunnel.tunnel_type!r}"
            )

        # Destination (user@host)
        destination = tunnel.ssh_host
        if tunnel.ssh_user:
            destination = f"{tunnel.ssh_user}@{tunnel.ssh_host}"
        cmd.append(destination)

        return cmd

    # ── lifecycle ────────────────────────────────────────────────

    def start_tunnel(self, tunnel: Tunnel) -> None:
        """Start *tunnel* as a background ``ssh`` process.

        The process is launched with ``stdin`` connected to ``/dev/null``
        and ``stdout``/``stderr`` piped so it does not block.

        Raises
        ------
        FileNotFoundError
            If the ``ssh`` binary is not found.
        RuntimeError
            If the tunnel is already running.
        """
        if self.is_tunnel_running(tunnel):
            raise RuntimeError(
                f"Tunnel {tunnel.name!r} is already running (PID {tunnel.pid})"
            )

        cmd = self.build_tunnel_command(tunnel)
        logger.info("Starting tunnel %r: %s", tunnel.name, " ".join(cmd))

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as exc:
            logger.exception("Failed to start tunnel %r", tunnel.name)
            tunnel.is_running = False
            tunnel.pid = None
            raise RuntimeError(
                f"Failed to start tunnel {tunnel.name!r}: {exc}"
            ) from exc

        tunnel.pid = proc.pid
        tunnel.is_running = True
        logger.info(
            "Tunnel %r started with PID %d", tunnel.name, proc.pid
        )

        # Monitor in background so we notice when the process exits.
        thread = threading.Thread(
            target=self._monitor, args=(tunnel, proc), daemon=True
        )
        thread.start()

    def stop_tunnel(self, tunnel: Tunnel) -> None:
        """Terminate *tunnel*'s background process (if running)."""
        if not self.is_tunnel_running(tunnel):
            return

        pid = tunnel.pid
        assert pid is not None  # guaranteed by is_tunnel_running() above
        logger.info("Stopping tunnel %r (PID %d)", tunnel.name, pid)

        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            logger.debug("PID %s already exited", pid)
        except OSError as exc:
            logger.warning(
                "Could not SIGTERM PID %s: %s", pid, exc
            )

        tunnel.is_running = False
        tunnel.pid = None

    def restart_tunnel(self, tunnel: Tunnel) -> None:
        """Stop and then start *tunnel*."""
        self.stop_tunnel(tunnel)
        self.start_tunnel(tunnel)

    def is_tunnel_running(self, tunnel: Tunnel) -> bool:
        """Return ``True`` if *tunnel*'s process is still alive."""
        if tunnel.pid is None:
            tunnel.is_running = False
            return False

        try:
            # Signal 0 checks existence without actually sending a signal.
            os.kill(tunnel.pid, 0)
        except ProcessLookupError:
            tunnel.is_running = False
            tunnel.pid = None
            return False
        except PermissionError:
            # Process exists but is owned by another user — treat as running.
            return True

        tunnel.is_running = True
        return True

    # ── bulk operations ──────────────────────────────────────────

    def start_auto_tunnels(self) -> None:
        """Start every tunnel whose ``auto_start`` flag is ``True``."""
        for tunnel in self.tunnels:
            if tunnel.auto_start and not self.is_tunnel_running(tunnel):
                try:
                    self.start_tunnel(tunnel)
                except (RuntimeError, FileNotFoundError):
                    logger.exception(
                        "Auto-start failed for tunnel %r", tunnel.name
                    )

    def stop_all_tunnels(self) -> None:
        """Stop every running tunnel."""
        for tunnel in self.tunnels:
            self.stop_tunnel(tunnel)

    def get_tunnel_status(self) -> dict[str, dict[str, Any]]:
        """Return a mapping of tunnel names to their current status.

        Returns
        -------
        dict[str, dict[str, Any]]
            Keys are tunnel names; values contain ``is_running``, ``pid``,
            and ``tunnel_type``.
        """
        status: dict[str, dict[str, Any]] = {}
        for tunnel in self.tunnels:
            self.is_tunnel_running(tunnel)
            status[tunnel.name] = {
                "is_running": tunnel.is_running,
                "pid": tunnel.pid,
                "tunnel_type": tunnel.tunnel_type,
                "local_port": tunnel.local_port,
            }
        return status

    # ── persistence ──────────────────────────────────────────────

    def save_tunnels(self, filepath: str) -> None:
        """Persist the tunnel list to a JSON file at *filepath*.

        Transient fields (``is_running``, ``pid``) are excluded.
        """
        data: list[dict[str, Any]] = []
        for tunnel in self.tunnels:
            d = asdict(tunnel)
            for key in _TRANSIENT_FIELDS:
                d.pop(key, None)
            data.append(d)

        try:
            os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            logger.info("Saved %d tunnel(s) to %s", len(data), filepath)
        except OSError as exc:
            logger.exception("Failed to save tunnels to %s", filepath)
            raise RuntimeError(
                f"Could not write tunnel file: {exc}"
            ) from exc

    def load_tunnels(self, filepath: str) -> None:
        """Load tunnels from *filepath*, replacing the current list.

        Unknown keys in the JSON are silently ignored so that files
        written by a newer version of the application can still be read.
        """
        try:
            with open(filepath, encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            logger.info("Tunnel file %s does not exist; starting empty", filepath)
            return
        except (json.JSONDecodeError, TypeError) as exc:
            logger.exception("Corrupt tunnel file %s", filepath)
            raise RuntimeError(
                f"Could not parse tunnel file: {exc}"
            ) from exc

        if not isinstance(data, list):
            logger.warning("Tunnel file %s has unexpected root type", filepath)
            return

        tunnels: list[Tunnel] = []
        valid_keys = {f.name for f in Tunnel.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        for entry in data:
            if not isinstance(entry, dict):
                logger.warning("Skipping non-dict entry in tunnel file")
                continue
            filtered = {k: v for k, v in entry.items() if k in valid_keys}
            try:
                tunnels.append(Tunnel(**filtered))
            except TypeError as exc:
                logger.warning("Skipping invalid tunnel entry: %s", exc)

        with self._lock:
            self.tunnels = tunnels
        logger.info("Loaded %d tunnel(s) from %s", len(tunnels), filepath)

    # ── private helpers ──────────────────────────────────────────

    @staticmethod
    def _monitor(tunnel: Tunnel, proc: subprocess.Popen[bytes]) -> None:
        """Wait for *proc* to exit and update *tunnel* state."""
        try:
            proc.wait()
        except Exception:  # noqa: BLE001
            logger.exception("Error while monitoring tunnel %r", tunnel.name)
        finally:
            if tunnel.pid == proc.pid:
                tunnel.is_running = False
                tunnel.pid = None
            logger.info(
                "Tunnel %r (PID %d) exited with code %s",
                tunnel.name,
                proc.pid,
                proc.returncode,
            )
