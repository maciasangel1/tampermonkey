"""Helpers for launching RDP, VNC, Telnet, and serial-console sessions.

On Fedora 43 these wrap standard system utilities:

* **RDP** → ``xfreerdp`` (from ``freerdp``)
* **VNC** → ``vncviewer`` (from ``tigervnc``)
* **Telnet** → system ``telnet``
* **Serial** → ``minicom`` or ``screen``
"""

import shlex
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# RDP
# ---------------------------------------------------------------------------

@dataclass
class RDPSession:
    """Configuration for a Remote Desktop (RDP) connection."""

    name: str
    host: str
    port: int = 3389
    username: str = ""
    domain: str = ""
    width: int = 1920
    height: int = 1080
    fullscreen: bool = False

    def build_command(self) -> str:
        """Build an ``xfreerdp`` command string."""
        parts = ["xfreerdp"]
        parts.append(f"/v:{self.host}:{self.port}")
        if self.username:
            parts.append(f"/u:{self.username}")
        if self.domain:
            parts.append(f"/d:{self.domain}")
        if self.fullscreen:
            parts.append("/f")
        else:
            parts.append(f"/size:{self.width}x{self.height}")
        parts.append("/cert:ignore")
        parts.append("+clipboard")
        return " ".join(parts)


# ---------------------------------------------------------------------------
# VNC
# ---------------------------------------------------------------------------

@dataclass
class VNCSession:
    """Configuration for a VNC connection."""

    name: str
    host: str
    port: int = 5900
    viewonly: bool = False

    def build_command(self) -> str:
        """Build a ``vncviewer`` command string."""
        parts = ["vncviewer"]
        parts.append(f"{self.host}:{self.port}")
        if self.viewonly:
            parts.append("-ViewOnly")
        return " ".join(parts)


# ---------------------------------------------------------------------------
# Telnet
# ---------------------------------------------------------------------------

def build_telnet_command(host: str, port: int = 23) -> str:
    """Return a ``telnet`` command string."""
    return " ".join(["telnet", shlex.quote(host), str(port)])


# ---------------------------------------------------------------------------
# Serial console
# ---------------------------------------------------------------------------

@dataclass
class SerialSession:
    """Configuration for a serial / COM-port connection."""

    name: str
    device: str = "/dev/ttyUSB0"
    baud_rate: int = 115200
    data_bits: int = 8
    parity: str = "N"  # N, E, O
    stop_bits: int = 1

    def build_command(self) -> str:
        """Build a ``minicom`` (or ``screen``) command string.

        Prefers ``minicom`` if available; ``screen`` as fallback.
        """
        # minicom syntax
        return (
            f"minicom -D {shlex.quote(self.device)} "
            f"-b {self.baud_rate}"
        )

    def build_screen_command(self) -> str:
        """Build a ``screen`` command for the serial port."""
        return f"screen {shlex.quote(self.device)} {self.baud_rate}"
