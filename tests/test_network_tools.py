"""Tests for fedoraxterm.network_tools module (pure-logic helpers only)."""

from unittest.mock import patch, MagicMock

from fedoraxterm.network_tools import (
    run_ping,
    run_traceroute,
    run_nslookup,
    scan_port,
    scan_ports,
    COMMON_PORTS,
)


class TestRunPing:
    """Tests for run_ping."""

    @patch("fedoraxterm.network_tools.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="PING ok\n3 packets transmitted",
            stderr="",
        )
        result = run_ping("localhost", count=3)
        assert "PING" in result
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["ping", "-c", "3", "localhost"]

    @patch("fedoraxterm.network_tools.subprocess.run", side_effect=FileNotFoundError)
    def test_command_not_found(self, _mock):
        result = run_ping("localhost")
        assert "not found" in result

    @patch(
        "fedoraxterm.network_tools.subprocess.run",
        side_effect=__import__("subprocess").TimeoutExpired(cmd="ping", timeout=30),
    )
    def test_timeout(self, _mock):
        result = run_ping("localhost")
        assert "timed out" in result


class TestRunTraceroute:
    """Tests for run_traceroute."""

    @patch("fedoraxterm.network_tools.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="traceroute to localhost", stderr="")
        result = run_traceroute("localhost")
        assert "traceroute" in result

    @patch("fedoraxterm.network_tools.subprocess.run", side_effect=FileNotFoundError)
    def test_not_installed(self, _mock):
        result = run_traceroute("localhost")
        assert "not found" in result


class TestRunNslookup:
    """Tests for run_nslookup."""

    @patch("fedoraxterm.network_tools.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="Server: 8.8.8.8", stderr="")
        result = run_nslookup("example.com")
        assert "8.8.8.8" in result

    @patch("fedoraxterm.network_tools.subprocess.run", side_effect=FileNotFoundError)
    def test_not_installed(self, _mock):
        result = run_nslookup("example.com")
        assert "not found" in result


class TestScanPort:
    """Tests for scan_port."""

    @patch("fedoraxterm.network_tools.socket.create_connection")
    def test_open_port(self, mock_conn):
        mock_conn.return_value.__enter__ = MagicMock()
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        assert scan_port("localhost", 22) is True

    @patch(
        "fedoraxterm.network_tools.socket.create_connection",
        side_effect=ConnectionRefusedError,
    )
    def test_closed_port(self, _mock):
        assert scan_port("localhost", 9999) is False

    @patch(
        "fedoraxterm.network_tools.socket.create_connection",
        side_effect=TimeoutError,
    )
    def test_timeout(self, _mock):
        assert scan_port("localhost", 9999, timeout=0.1) is False


class TestScanPorts:
    """Tests for scan_ports."""

    @patch("fedoraxterm.network_tools.scan_port")
    def test_multiple_ports(self, mock_scan):
        mock_scan.side_effect = [True, False, True]
        result = scan_ports("localhost", [22, 23, 80])
        assert result == {22: True, 23: False, 80: True}
        assert mock_scan.call_count == 3


class TestCommonPorts:
    """Tests for the COMMON_PORTS list."""

    def test_contains_well_known_ports(self):
        assert 22 in COMMON_PORTS   # SSH
        assert 80 in COMMON_PORTS   # HTTP
        assert 443 in COMMON_PORTS  # HTTPS
        assert 3389 in COMMON_PORTS # RDP

    def test_all_valid_range(self):
        for port in COMMON_PORTS:
            assert 1 <= port <= 65535
