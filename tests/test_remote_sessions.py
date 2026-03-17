"""Tests for fedoraxterm.remote_sessions module."""

from fedoraxterm.remote_sessions import (
    RDPSession,
    VNCSession,
    SerialSession,
    build_telnet_command,
)


class TestRDPSession:
    """Tests for RDPSession."""

    def test_basic_command(self):
        rdp = RDPSession(name="test", host="10.0.0.1")
        cmd = rdp.build_command()
        assert "xfreerdp" in cmd
        assert "/v:10.0.0.1:3389" in cmd

    def test_with_username(self):
        rdp = RDPSession(name="test", host="10.0.0.1", username="admin")
        cmd = rdp.build_command()
        assert "/u:admin" in cmd

    def test_with_domain(self):
        rdp = RDPSession(name="test", host="10.0.0.1", domain="CORP")
        cmd = rdp.build_command()
        assert "/d:CORP" in cmd

    def test_fullscreen(self):
        rdp = RDPSession(name="test", host="10.0.0.1", fullscreen=True)
        cmd = rdp.build_command()
        assert "/f" in cmd
        assert "/size:" not in cmd

    def test_custom_resolution(self):
        rdp = RDPSession(name="test", host="10.0.0.1", width=1280, height=720)
        cmd = rdp.build_command()
        assert "/size:1280x720" in cmd

    def test_clipboard_enabled(self):
        rdp = RDPSession(name="test", host="10.0.0.1")
        cmd = rdp.build_command()
        assert "+clipboard" in cmd


class TestVNCSession:
    """Tests for VNCSession."""

    def test_basic_command(self):
        vnc = VNCSession(name="test", host="10.0.0.1")
        cmd = vnc.build_command()
        assert "vncviewer" in cmd
        assert "10.0.0.1:5900" in cmd

    def test_custom_port(self):
        vnc = VNCSession(name="test", host="10.0.0.1", port=5901)
        cmd = vnc.build_command()
        assert "10.0.0.1:5901" in cmd

    def test_viewonly(self):
        vnc = VNCSession(name="test", host="10.0.0.1", viewonly=True)
        cmd = vnc.build_command()
        assert "-ViewOnly" in cmd


class TestBuildTelnetCommand:
    """Tests for build_telnet_command."""

    def test_basic(self):
        cmd = build_telnet_command("10.0.0.1")
        assert "telnet" in cmd
        assert "10.0.0.1" in cmd
        assert "23" in cmd

    def test_custom_port(self):
        cmd = build_telnet_command("10.0.0.1", port=2323)
        assert "2323" in cmd


class TestSerialSession:
    """Tests for SerialSession."""

    def test_defaults(self):
        s = SerialSession(name="test")
        assert s.device == "/dev/ttyUSB0"
        assert s.baud_rate == 115200

    def test_minicom_command(self):
        s = SerialSession(name="test", device="/dev/ttyS0", baud_rate=9600)
        cmd = s.build_command()
        assert "minicom" in cmd
        assert "/dev/ttyS0" in cmd
        assert "9600" in cmd

    def test_screen_command(self):
        s = SerialSession(name="test", device="/dev/ttyUSB0", baud_rate=115200)
        cmd = s.build_screen_command()
        assert "screen" in cmd
        assert "/dev/ttyUSB0" in cmd
        assert "115200" in cmd
