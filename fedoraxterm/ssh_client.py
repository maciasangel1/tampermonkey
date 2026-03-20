"""SSH command builder for FedoraXTerm.

Translates :class:`~fedoraxterm.settings.SSHSession` configuration into
concrete ``ssh``, ``sftp``, ``scp``, and tunnel command-line invocations
suitable for :func:`subprocess.Popen`.
"""

from __future__ import annotations

import re
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fedoraxterm.settings import SSHSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONN_RE = re.compile(
    r"^(?:(?P<user>[^@]+)@)?(?P<host>[^:]+)(?::(?P<port>\d+))?$"
)


def _find_binary(name: str) -> str:
    """Return the absolute path of *name*, falling back to bare name."""
    return shutil.which(name) or name


def _common_options(session: SSHSession) -> list[str]:
    """Return ``-o`` / flag options shared by ssh, sftp and scp."""
    opts: list[str] = []

    # Port (-p for ssh; callers patch to -P for sftp/scp)
    if session.port and session.port != 22:
        opts += ["-p", str(session.port)]

    # Identity / key auth
    if session.auth_method == "publickey" and session.private_key_path:
        opts += ["-i", session.private_key_path]

    # Agent forwarding
    if session.use_agent_forwarding:
        opts.append("-A")

    # X11 forwarding
    if session.x11_forwarding:
        opts.append("-X")

    # Compression
    if session.compression:
        opts.append("-C")

    # Keep-alive
    if session.send_keepalive:
        opts += [
            "-o", f"ServerAliveInterval={session.keepalive_interval}",
            "-o", "ServerAliveCountMax=3",
        ]

    # Accept new host keys automatically (SecureCRT default behaviour)
    opts += ["-o", "StrictHostKeyChecking=accept-new"]

    # Jump host / ProxyJump
    if session.jump_host:
        jump = session.jump_host
        if session.jump_user:
            jump = f"{session.jump_user}@{jump}"
        if session.jump_port and session.jump_port != 22:
            jump = f"{jump}:{session.jump_port}"
        opts += ["-J", jump]

    # SOCKS / HTTP proxy via ProxyCommand
    proxy_cmd = _build_proxy_command(session)
    if proxy_cmd:
        opts += ["-o", f"ProxyCommand={proxy_cmd}"]

    return opts


def _build_proxy_command(session: SSHSession) -> str:
    """Build a ``ProxyCommand`` string for firewall/proxy settings.

    Returns an empty string when no proxy is configured.
    """
    if session.firewall_type == "none" or not session.firewall_host:
        return ""

    fw_type = session.firewall_type.lower()
    host = session.firewall_host
    port = session.firewall_port or 1080

    if fw_type in ("socks4", "socks5"):
        # Prefer ncat, fall back to connect-proxy
        ncat = shutil.which("ncat") or shutil.which("nc")
        if ncat:
            proxy_type = "socks5" if fw_type == "socks5" else "socks4"
            return (
                f"{ncat} --proxy-type {proxy_type} "
                f"--proxy {host}:{port} %h %p"
            )
        connect = shutil.which("connect-proxy") or "connect-proxy"
        flag = "-S" if fw_type == "socks5" else "-4 -S"
        return f"{connect} {flag} {host}:{port} %h %p"

    if fw_type == "http":
        connect = shutil.which("connect-proxy") or "connect-proxy"
        auth = ""
        if session.firewall_user:
            auth = f"-H {session.firewall_user}@ "
        return f"{connect} -H {host}:{port} {auth}%h %p"

    return ""


def _destination(session: SSHSession) -> str:
    """Return ``[user@]hostname`` for the session."""
    if session.username:
        return f"{session.username}@{session.hostname}"
    return session.hostname


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_ssh_command(session: SSHSession) -> list[str]:
    """Build an ``ssh`` command from *session* configuration.

    Returns a list of strings ready for :func:`subprocess.Popen`.
    """
    cmd: list[str] = [_find_binary("ssh")]
    cmd += _common_options(session)

    # Custom encoding conveyed via SendEnv + locale (best-effort)
    if session.encoding and session.encoding.lower() != "utf-8":
        cmd += ["-o", f"SendEnv=LANG={session.encoding}"]

    cmd.append(_destination(session))

    # Auto-command (run on remote host)
    if session.auto_command:
        cmd.append(session.auto_command)

    return cmd


def build_sftp_command(session: SSHSession) -> list[str]:
    """Build an ``sftp`` command from *session* configuration.

    Returns a list of strings ready for :func:`subprocess.Popen`.
    """
    cmd: list[str] = [_find_binary("sftp")]

    # sftp uses -P for port (same flag letter, capital P)
    opts = _common_options(session)
    opts = ["-P" if o == "-p" else o for o in opts]
    cmd += opts

    cmd.append(_destination(session))
    return cmd


def build_scp_command(
    session: SSHSession,
    source: str,
    dest: str,
    recursive: bool = False,
) -> list[str]:
    """Build an ``scp`` command for file transfer.

    Either *source* or *dest* should be a remote path prefixed with the
    host (e.g. ``user@host:/path``).  If neither contains ``:``, the
    destination is assumed to be remote.

    Returns a list of strings ready for :func:`subprocess.Popen`.
    """
    cmd: list[str] = [_find_binary("scp")]

    # scp uses -P (capital) for port
    opts = _common_options(session)
    opts = ["-P" if o == "-p" else o for o in opts]
    cmd += opts

    if recursive:
        cmd.append("-r")

    # If neither path looks remote, prefix dest with host
    if ":" not in source and ":" not in dest:
        dest = f"{_destination(session)}:{dest}"

    cmd += [source, dest]
    return cmd


def build_tunnel_command(
    session: SSHSession,
    local_port: int,
    remote_host: str,
    remote_port: int,
    reverse: bool = False,
) -> list[str]:
    """Build an SSH port-forwarding command (``-L`` or ``-R``).

    When *reverse* is ``True`` a remote-to-local tunnel (``-R``) is
    created; otherwise a local-to-remote tunnel (``-L``).

    Returns a list of strings ready for :func:`subprocess.Popen`.
    """
    cmd: list[str] = [_find_binary("ssh")]
    cmd += _common_options(session)

    flag = "-R" if reverse else "-L"
    spec = f"{local_port}:{remote_host}:{remote_port}"
    cmd += [flag, spec, "-N", _destination(session)]
    return cmd


def build_dynamic_tunnel_command(
    session: SSHSession,
    local_port: int,
) -> list[str]:
    """Build a SOCKS proxy tunnel command (``-D``).

    Returns a list of strings ready for :func:`subprocess.Popen`.
    """
    cmd: list[str] = [_find_binary("ssh")]
    cmd += _common_options(session)
    cmd += ["-D", str(local_port), "-N", _destination(session)]
    return cmd


def parse_connection_string(conn_str: str) -> tuple[str, int, str]:
    """Parse a connection string into ``(hostname, port, username)``.

    Accepted formats::

        host
        host:port
        user@host
        user@host:port

    Returns ``("", 22, "")`` for parts that are not present.

    Raises :class:`ValueError` for unparseable strings.
    """
    conn_str = conn_str.strip()
    if not conn_str:
        raise ValueError("Empty connection string")

    match = _CONN_RE.match(conn_str)
    if not match:
        raise ValueError(f"Cannot parse connection string: {conn_str!r}")

    username = match.group("user") or ""
    hostname = match.group("host") or ""
    port_str = match.group("port")
    port = int(port_str) if port_str else 22

    if not hostname:
        raise ValueError(f"No hostname in connection string: {conn_str!r}")

    return hostname, port, username
