"""Remote session protocol builders for various connection types."""
from __future__ import annotations

import shutil
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RDPSession:
    """Builds xfreerdp command for RDP connections."""

    hostname: str
    port: int = 3389
    username: Optional[str] = None
    domain: Optional[str] = None
    resolution: Optional[str] = None
    color_depth: int = 32
    fullscreen: bool = False

    def build_command(self) -> list[str]:
        """Build the xfreerdp command line."""
        cmd = ["xfreerdp", f"/v:{self.hostname}:{self.port}"]
        if self.username:
            cmd.append(f"/u:{self.username}")
        if self.domain:
            cmd.append(f"/d:{self.domain}")
        if self.resolution:
            cmd.append(f"/size:{self.resolution}")
        cmd.append(f"/bpp:{self.color_depth}")
        if self.fullscreen:
            cmd.append("/f")
        # NLA authentication
        cmd.append("/sec:nla")
        # Drive redirect (home directory)
        cmd.append("/drive:home,/home")
        # Clipboard support
        cmd.append("+clipboard")
        # Audio redirection
        cmd.append("/sound:sys:pulse")
        return cmd

    def description(self) -> str:
        """Return a human-readable summary of this session."""
        parts = [f"RDP session to {self.hostname}:{self.port}"]
        if self.username:
            user = f"{self.domain}\\{self.username}" if self.domain else self.username
            parts.append(f"as {user}")
        if self.fullscreen:
            parts.append("(fullscreen)")
        elif self.resolution:
            parts.append(f"at {self.resolution}")
        return " ".join(parts)


@dataclass
class VNCSession:
    """Builds vncviewer command for VNC connections."""

    hostname: str
    port: int = 5900
    password_file: Optional[str] = None
    quality: Optional[int] = None
    fullscreen: bool = False
    view_only: bool = False

    def build_command(self) -> list[str]:
        """Build the vncviewer command line."""
        cmd = ["vncviewer", f"{self.hostname}:{self.port}"]
        if self.password_file:
            cmd.extend(["-passwd", self.password_file])
        if self.quality is not None:
            cmd.extend(["-quality", str(self.quality)])
        if self.fullscreen:
            cmd.append("-fullscreen")
        if self.view_only:
            cmd.append("-viewonly")
        return cmd

    def description(self) -> str:
        """Return a human-readable summary of this session."""
        parts = [f"VNC session to {self.hostname}:{self.port}"]
        if self.view_only:
            parts.append("(view-only)")
        if self.fullscreen:
            parts.append("(fullscreen)")
        return " ".join(parts)


@dataclass
class TelnetSession:
    """Builds telnet command for Telnet connections."""

    hostname: str
    port: int = 23
    terminal_type: Optional[str] = None

    def build_command(self) -> list[str]:
        """Build the telnet command line."""
        cmd = ["telnet"]
        if self.terminal_type:
            cmd.extend(["-T", self.terminal_type])
        cmd.extend([self.hostname, str(self.port)])
        return cmd

    def description(self) -> str:
        """Return a human-readable summary of this session."""
        parts = [f"Telnet session to {self.hostname}:{self.port}"]
        if self.terminal_type:
            parts.append(f"(terminal: {self.terminal_type})")
        return " ".join(parts)


@dataclass
class SerialSession:
    """Builds minicom or screen command for serial connections."""

    port: str = "/dev/ttyUSB0"
    baud_rate: int = 9600
    data_bits: int = 8
    stop_bits: int = 1
    parity: str = "none"
    flow_control: str = "none"
    backend: str = "minicom"

    def build_command(self) -> list[str]:
        """Build the serial terminal command line.

        Supports both minicom and screen as backends.
        """
        if self.backend == "screen":
            return self._build_screen_command()
        return self._build_minicom_command()

    def _build_minicom_command(self) -> list[str]:
        """Build minicom command."""
        cmd = ["minicom", "-D", self.port, "-b", str(self.baud_rate)]
        parity_map = {"none": "8N1", "even": "8E1", "odd": "8O1"}
        setting = parity_map.get(self.parity, "8N1")
        # Adjust data bits in the setting string
        setting = str(self.data_bits) + setting[1:]
        cmd.extend(["-8"])
        if self.flow_control == "none":
            cmd.append("-w")
        return cmd

    def _build_screen_command(self) -> list[str]:
        """Build screen command."""
        baud_config = str(self.baud_rate)
        parity_char = {"none": "n", "even": "e", "odd": "o"}.get(self.parity, "n")
        flow_char = {"none": "-", "hardware": "h", "software": "s"}.get(
            self.flow_control, "-"
        )
        settings = f"{baud_config},cs{self.data_bits},parenb" if self.parity != "none" else baud_config
        cmd = ["screen", self.port, settings]
        return cmd

    def description(self) -> str:
        """Return a human-readable summary of this session."""
        return (
            f"Serial session on {self.port} at {self.baud_rate} baud "
            f"({self.data_bits}{self.parity[0].upper()}{self.stop_bits}, "
            f"flow: {self.flow_control}, backend: {self.backend})"
        )


@dataclass
class RawSession:
    """Builds nc/ncat command for raw socket connections."""

    hostname: str
    port: int = 0

    def build_command(self) -> list[str]:
        """Build the nc/ncat command line for a raw socket connection."""
        binary = "ncat" if shutil.which("ncat") else "nc"
        return [binary, self.hostname, str(self.port)]

    def description(self) -> str:
        """Return a human-readable summary of this session."""
        return f"Raw socket connection to {self.hostname}:{self.port}"


@dataclass
class RloginSession:
    """Builds rlogin command for rlogin connections."""

    hostname: str
    port: int = 513
    username: Optional[str] = None

    def build_command(self) -> list[str]:
        """Build the rlogin command line."""
        cmd = ["rlogin", self.hostname]
        if self.port != 513:
            cmd.extend(["-p", str(self.port)])
        if self.username:
            cmd.extend(["-l", self.username])
        return cmd

    def description(self) -> str:
        """Return a human-readable summary of this session."""
        parts = [f"Rlogin session to {self.hostname}:{self.port}"]
        if self.username:
            parts.append(f"as {self.username}")
        return " ".join(parts)


# Map protocol names to the binaries they require
_PROTOCOL_BINARIES: dict[str, list[str]] = {
    "rdp": ["xfreerdp"],
    "vnc": ["vncviewer"],
    "telnet": ["telnet"],
    "serial": ["minicom", "screen"],
    "raw": ["nc", "ncat"],
    "rlogin": ["rlogin"],
}


def check_protocol_available(protocol: str) -> bool:
    """Check if the required binary for a protocol is installed.

    Args:
        protocol: One of 'rdp', 'vnc', 'telnet', 'serial', 'raw', 'rlogin'.

    Returns:
        True if at least one required binary is found on PATH.
    """
    binaries = _PROTOCOL_BINARIES.get(protocol.lower())
    if binaries is None:
        logger.warning("Unknown protocol: %s", protocol)
        return False
    return any(shutil.which(b) is not None for b in binaries)
