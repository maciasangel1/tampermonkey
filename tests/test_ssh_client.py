"""Tests for fedoraxterm.ssh_client module."""

from fedoraxterm.ssh_client import build_ssh_command, build_sftp_command


class TestBuildSSHCommand:
    """Tests for build_ssh_command."""

    def test_basic(self):
        cmd = build_ssh_command(host="example.com")
        assert "ssh" in cmd
        assert "example.com" in cmd

    def test_with_username(self):
        cmd = build_ssh_command(host="example.com", username="admin")
        assert "admin@example.com" in cmd

    def test_custom_port(self):
        cmd = build_ssh_command(host="example.com", port=2222)
        assert "-p" in cmd
        assert "2222" in cmd

    def test_default_port_no_flag(self):
        cmd = build_ssh_command(host="example.com", port=22)
        assert "-p" not in cmd

    def test_key_auth(self):
        cmd = build_ssh_command(
            host="example.com",
            auth_method="key",
            private_key_path="/home/user/.ssh/id_rsa",
        )
        assert "-i" in cmd
        assert "/home/user/.ssh/id_rsa" in cmd

    def test_password_auth_no_key_flag(self):
        cmd = build_ssh_command(host="example.com", auth_method="password")
        assert "-i" not in cmd

    def test_extra_opts(self):
        cmd = build_ssh_command(host="example.com", extra_opts="-v -o StrictHostKeyChecking=no")
        assert "-v" in cmd
        assert "StrictHostKeyChecking=no" in cmd


class TestBuildSFTPCommand:
    """Tests for build_sftp_command."""

    def test_basic(self):
        cmd = build_sftp_command(host="example.com")
        assert "sftp" in cmd
        assert "example.com" in cmd

    def test_with_username(self):
        cmd = build_sftp_command(host="example.com", username="admin")
        assert "admin@example.com" in cmd

    def test_custom_port(self):
        cmd = build_sftp_command(host="example.com", port=2222)
        assert "-P" in cmd  # SFTP uses uppercase -P
        assert "2222" in cmd

    def test_with_key(self):
        cmd = build_sftp_command(
            host="example.com", private_key_path="/path/to/key"
        )
        assert "-i" in cmd
        assert "/path/to/key" in cmd
