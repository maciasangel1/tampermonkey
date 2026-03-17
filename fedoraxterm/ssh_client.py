"""SSH connection helpers for FedoraXTerm."""

import shlex


def build_ssh_command(
    host: str,
    port: int = 22,
    username: str = "",
    auth_method: str = "password",
    private_key_path: str = "",
    extra_opts: str = "",
) -> str:
    """Build an OpenSSH command string for spawning in the terminal.

    This delegates to the system ``ssh`` binary so that we get proper
    pseudo-terminal allocation, agent forwarding, etc.

    Args:
        host: Remote hostname or IP address.
        port: SSH port number.
        username: Remote username (optional).
        auth_method: ``"password"`` or ``"key"``.
        private_key_path: Path to private key file (used when *auth_method* is ``"key"``).
        extra_opts: Any additional flags to pass to ``ssh``.

    Returns:
        A shell command string suitable for :func:`shlex.split`.
    """
    parts = ["ssh"]

    if port != 22:
        parts.extend(["-p", str(port)])

    if auth_method == "key" and private_key_path:
        parts.extend(["-i", private_key_path])

    if extra_opts:
        parts.extend(shlex.split(extra_opts))

    destination = f"{username}@{host}" if username else host
    parts.append(destination)

    return " ".join(shlex.quote(p) for p in parts)


def build_sftp_command(
    host: str,
    port: int = 22,
    username: str = "",
    private_key_path: str = "",
) -> str:
    """Build an ``sftp`` command string.

    Args:
        host: Remote hostname or IP address.
        port: SFTP port number.
        username: Remote username (optional).
        private_key_path: Path to private key file (optional).

    Returns:
        A shell command string.
    """
    parts = ["sftp"]

    if port != 22:
        parts.extend(["-P", str(port)])

    if private_key_path:
        parts.extend(["-i", private_key_path])

    destination = f"{username}@{host}" if username else host
    parts.append(destination)

    return " ".join(shlex.quote(p) for p in parts)
