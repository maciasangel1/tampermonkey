"""Network diagnostic tools for FedoraXTerm.

Provides ping, traceroute, NSLookup, port-scanning, and WHOIS
utilities that mirror the toolbox found in SecureCRT.  Every tool
runs its work in a background thread and delivers results (or
progress updates) through an optional *callback*.
"""

from __future__ import annotations

import logging
import re
import shutil
import socket
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ── result dataclasses ───────────────────────────────────────────

@dataclass
class PingResult:
    """Parsed result of a ping run."""

    host: str = ""
    packets_sent: int = 0
    packets_received: int = 0
    packet_loss: float = 0.0
    min_ms: float = 0.0
    avg_ms: float = 0.0
    max_ms: float = 0.0
    mdev_ms: float = 0.0
    raw_output: str = ""
    error: Optional[str] = None


@dataclass
class TracerouteHop:
    """A single hop returned by traceroute."""

    hop_number: int = 0
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    rtt_ms: list[float] = field(default_factory=list)
    is_timeout: bool = False


@dataclass
class TracerouteResult:
    """Full traceroute result."""

    host: str = ""
    hops: list[TracerouteHop] = field(default_factory=list)
    raw_output: str = ""
    error: Optional[str] = None


@dataclass
class NSLookupResult:
    """Parsed DNS lookup result."""

    host: str = ""
    addresses: list[str] = field(default_factory=list)
    canonical_name: Optional[str] = None
    dns_server: Optional[str] = None
    raw_output: str = ""
    error: Optional[str] = None


@dataclass
class PortResult:
    """Result for a single port probe."""

    port: int = 0
    is_open: bool = False
    service_name: str = ""
    error: Optional[str] = None


@dataclass
class WhoisResult:
    """Parsed WHOIS result."""

    host: str = ""
    raw_output: str = ""
    registrar: Optional[str] = None
    creation_date: Optional[str] = None
    expiration_date: Optional[str] = None
    error: Optional[str] = None


# ── helpers ──────────────────────────────────────────────────────

def _find_binary(name: str) -> Optional[str]:
    """Return the full path of *name* or ``None`` if not installed."""
    return shutil.which(name)


def _run_command(
    cmd: list[str],
    timeout: int,
) -> tuple[str, Optional[str]]:
    """Execute *cmd* and return ``(stdout, error_string | None)``."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = proc.stdout + proc.stderr
        return output, None
    except FileNotFoundError:
        binary = cmd[0] if cmd else "<unknown>"
        msg = f"Command not found: {binary}"
        logger.warning(msg)
        return "", msg
    except subprocess.TimeoutExpired:
        msg = f"Command timed out after {timeout}s"
        logger.warning(msg)
        return "", msg
    except OSError as exc:
        msg = f"OS error running command: {exc}"
        logger.exception(msg)
        return "", msg


def _run_in_thread(
    target: Callable[..., Any],
    callback: Optional[Callable[..., Any]],
    *args: Any,
    **kwargs: Any,
) -> threading.Thread:
    """Run *target* in a daemon thread; pass its return value to *callback*."""

    def _wrapper() -> None:
        result = target(*args, **kwargs)
        if callback is not None:
            callback(result)

    thread = threading.Thread(target=_wrapper, daemon=True)
    thread.start()
    return thread


# ── PingTool ─────────────────────────────────────────────────────

class PingTool:
    """Asynchronous wrapper around the system ``ping`` command."""

    def run(
        self,
        host: str,
        count: int = 4,
        timeout: int = 5,
        callback: Optional[Callable[[PingResult], None]] = None,
    ) -> threading.Thread:
        """Ping *host* in a background thread.

        Parameters
        ----------
        host:
            Target hostname or IP address.
        count:
            Number of ICMP echo requests.
        timeout:
            Per-packet timeout in seconds.
        callback:
            Called with the :class:`PingResult` when finished.

        Returns
        -------
        threading.Thread
            The background thread (already started).
        """
        return _run_in_thread(self._execute, callback, host, count, timeout)

    # ── internals ────────────────────────────────────────────────

    def _execute(self, host: str, count: int, timeout: int) -> PingResult:
        binary = _find_binary("ping")
        if binary is None:
            return PingResult(host=host, error="ping: command not found")

        cmd = [binary, "-c", str(count), "-W", str(timeout), host]
        overall_timeout = (timeout + 1) * count + 5
        output, error = _run_command(cmd, timeout=overall_timeout)

        if error is not None:
            return PingResult(host=host, raw_output=output, error=error)

        return self._parse(host, output)

    @staticmethod
    def _parse(host: str, output: str) -> PingResult:
        result = PingResult(host=host, raw_output=output)

        loss_match = re.search(
            r"(\d+)\s+packets?\s+transmitted.*?(\d+)\s+received.*?"
            r"([\d.]+)%\s+packet\s+loss",
            output,
            re.DOTALL,
        )
        if loss_match:
            result.packets_sent = int(loss_match.group(1))
            result.packets_received = int(loss_match.group(2))
            result.packet_loss = float(loss_match.group(3))

        rtt_match = re.search(
            r"rtt\s+min/avg/max/mdev\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)",
            output,
        )
        if rtt_match:
            result.min_ms = float(rtt_match.group(1))
            result.avg_ms = float(rtt_match.group(2))
            result.max_ms = float(rtt_match.group(3))
            result.mdev_ms = float(rtt_match.group(4))

        return result


# ── TracerouteTool ───────────────────────────────────────────────

class TracerouteTool:
    """Asynchronous wrapper around the system ``traceroute`` command."""

    def run(
        self,
        host: str,
        max_hops: int = 30,
        timeout: int = 5,
        callback: Optional[Callable[[TracerouteResult], None]] = None,
    ) -> threading.Thread:
        """Trace the route to *host* in a background thread.

        Parameters
        ----------
        host:
            Target hostname or IP address.
        max_hops:
            Maximum TTL (hop limit).
        timeout:
            Per-probe timeout in seconds.
        callback:
            Called with the :class:`TracerouteResult` when finished.

        Returns
        -------
        threading.Thread
            The background thread (already started).
        """
        return _run_in_thread(self._execute, callback, host, max_hops, timeout)

    def _execute(
        self, host: str, max_hops: int, timeout: int
    ) -> TracerouteResult:
        binary = _find_binary("traceroute")
        if binary is None:
            return TracerouteResult(
                host=host, error="traceroute: command not found"
            )

        cmd = [binary, "-m", str(max_hops), "-w", str(timeout), host]
        overall_timeout = max_hops * timeout + 10
        output, error = _run_command(cmd, timeout=overall_timeout)

        if error is not None:
            return TracerouteResult(host=host, raw_output=output, error=error)

        return self._parse(host, output)

    @staticmethod
    def _parse(host: str, output: str) -> TracerouteResult:
        result = TracerouteResult(host=host, raw_output=output)

        for line in output.splitlines():
            line = line.strip()
            if not line or line.startswith("traceroute"):
                continue

            hop_match = re.match(r"^\s*(\d+)\s+(.*)$", line)
            if not hop_match:
                continue

            hop_number = int(hop_match.group(1))
            rest = hop_match.group(2)

            if rest.strip() == "* * *":
                result.hops.append(
                    TracerouteHop(hop_number=hop_number, is_timeout=True)
                )
                continue

            hop = TracerouteHop(hop_number=hop_number)

            # hostname (ip)  rtt1 ms  rtt2 ms  rtt3 ms
            host_match = re.match(
                r"(\S+)\s+\((\d+\.\d+\.\d+\.\d+)\)", rest
            )
            if host_match:
                hop.hostname = host_match.group(1)
                hop.ip_address = host_match.group(2)

            for rtt in re.findall(r"([\d.]+)\s+ms", rest):
                hop.rtt_ms.append(float(rtt))

            result.hops.append(hop)

        return result


# ── NSLookupTool ─────────────────────────────────────────────────

class NSLookupTool:
    """Asynchronous DNS lookup using ``nslookup`` or ``dig``."""

    def run(
        self,
        host: str,
        dns_server: Optional[str] = None,
        callback: Optional[Callable[[NSLookupResult], None]] = None,
    ) -> threading.Thread:
        """Look up *host* in a background thread.

        Parameters
        ----------
        host:
            Hostname to resolve.
        dns_server:
            Optional DNS server to query.
        callback:
            Called with the :class:`NSLookupResult` when finished.

        Returns
        -------
        threading.Thread
            The background thread (already started).
        """
        return _run_in_thread(self._execute, callback, host, dns_server)

    def _execute(
        self, host: str, dns_server: Optional[str]
    ) -> NSLookupResult:
        # Prefer dig, fall back to nslookup.
        dig = _find_binary("dig")
        if dig is not None:
            return self._run_dig(dig, host, dns_server)

        nslookup = _find_binary("nslookup")
        if nslookup is not None:
            return self._run_nslookup(nslookup, host, dns_server)

        return NSLookupResult(
            host=host,
            error="Neither dig nor nslookup found on this system",
        )

    # ── dig backend ──────────────────────────────────────────────

    @staticmethod
    def _run_dig(
        binary: str, host: str, dns_server: Optional[str]
    ) -> NSLookupResult:
        cmd: list[str] = [binary, host]
        if dns_server:
            cmd.insert(1, f"@{dns_server}")

        output, error = _run_command(cmd, timeout=15)
        if error is not None:
            return NSLookupResult(host=host, raw_output=output, error=error)

        result = NSLookupResult(
            host=host, raw_output=output, dns_server=dns_server
        )

        for line in output.splitlines():
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            # A/AAAA records: <name> <ttl> IN A <address>
            a_match = re.match(
                r"\S+\s+\d+\s+IN\s+(?:A|AAAA)\s+(\S+)", line
            )
            if a_match:
                result.addresses.append(a_match.group(1))

            cname_match = re.match(
                r"\S+\s+\d+\s+IN\s+CNAME\s+(\S+)", line
            )
            if cname_match:
                result.canonical_name = cname_match.group(1).rstrip(".")

        return result

    # ── nslookup backend ─────────────────────────────────────────

    @staticmethod
    def _run_nslookup(
        binary: str, host: str, dns_server: Optional[str]
    ) -> NSLookupResult:
        cmd: list[str] = [binary, host]
        if dns_server:
            cmd.append(dns_server)

        output, error = _run_command(cmd, timeout=15)
        if error is not None:
            return NSLookupResult(host=host, raw_output=output, error=error)

        result = NSLookupResult(
            host=host, raw_output=output, dns_server=dns_server
        )

        # nslookup prints "Name: … Address: …" in the answer section.
        in_answer = False
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("Name:"):
                in_answer = True
                name = stripped.split(":", 1)[1].strip()
                if result.canonical_name is None and name != host:
                    result.canonical_name = name
            elif in_answer and stripped.startswith("Address:"):
                addr = stripped.split(":", 1)[1].strip()
                result.addresses.append(addr)

        return result


# ── PortScanner ──────────────────────────────────────────────────

class PortScanner:
    """Threaded TCP port scanner."""

    COMMON_PORTS: dict[int, str] = {
        20: "ftp-data",
        21: "ftp",
        22: "ssh",
        23: "telnet",
        25: "smtp",
        53: "dns",
        80: "http",
        110: "pop3",
        119: "nntp",
        123: "ntp",
        143: "imap",
        161: "snmp",
        194: "irc",
        443: "https",
        445: "smb",
        465: "smtps",
        514: "syslog",
        587: "submission",
        631: "ipp",
        993: "imaps",
        995: "pop3s",
        1433: "mssql",
        1521: "oracle",
        3306: "mysql",
        3389: "rdp",
        5432: "postgresql",
        5900: "vnc",
        6379: "redis",
        8080: "http-alt",
        8443: "https-alt",
        27017: "mongodb",
    }

    def scan(
        self,
        host: str,
        ports: list[int],
        timeout: int = 2,
        callback: Optional[Callable[[list[PortResult]], None]] = None,
    ) -> threading.Thread:
        """Scan *ports* on *host* in a background thread.

        Parameters
        ----------
        host:
            Target hostname or IP address.
        ports:
            List of TCP port numbers to probe.
        timeout:
            Per-port connection timeout in seconds.
        callback:
            Called with a list of :class:`PortResult` when finished.

        Returns
        -------
        threading.Thread
            The background thread (already started).
        """
        return _run_in_thread(self._execute, callback, host, ports, timeout)

    def _execute(
        self, host: str, ports: list[int], timeout: int
    ) -> list[PortResult]:
        results: list[PortResult] = []
        max_workers = min(len(ports), 50) if ports else 1

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(self._probe, host, port, timeout): port
                for port in ports
            }
            for future in as_completed(futures):
                results.append(future.result())

        results.sort(key=lambda r: r.port)
        return results

    def _probe(self, host: str, port: int, timeout: int) -> PortResult:
        service = self.COMMON_PORTS.get(port, "")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            errno = sock.connect_ex((host, port))
            sock.close()
            return PortResult(port=port, is_open=(errno == 0), service_name=service)
        except socket.gaierror as exc:
            return PortResult(port=port, service_name=service, error=str(exc))
        except OSError as exc:
            return PortResult(port=port, service_name=service, error=str(exc))


# ── WhoisTool ────────────────────────────────────────────────────

class WhoisTool:
    """Asynchronous WHOIS lookup using the system ``whois`` command."""

    def run(
        self,
        host: str,
        callback: Optional[Callable[[WhoisResult], None]] = None,
    ) -> threading.Thread:
        """Query WHOIS for *host* in a background thread.

        Parameters
        ----------
        host:
            Domain name or IP address.
        callback:
            Called with the :class:`WhoisResult` when finished.

        Returns
        -------
        threading.Thread
            The background thread (already started).
        """
        return _run_in_thread(self._execute, callback, host)

    def _execute(self, host: str) -> WhoisResult:
        binary = _find_binary("whois")
        if binary is None:
            return WhoisResult(host=host, error="whois: command not found")

        output, error = _run_command([binary, host], timeout=30)
        if error is not None:
            return WhoisResult(host=host, raw_output=output, error=error)

        return self._parse(host, output)

    @staticmethod
    def _parse(host: str, output: str) -> WhoisResult:
        result = WhoisResult(host=host, raw_output=output)

        for line in output.splitlines():
            lower = line.lower().strip()

            if lower.startswith("registrar:"):
                result.registrar = line.split(":", 1)[1].strip()
            elif "creation date:" in lower:
                result.creation_date = line.split(":", 1)[1].strip()
            elif "expir" in lower and "date:" in lower:
                result.expiration_date = line.split(":", 1)[1].strip()

        return result
