"""Tests for fedoraxterm.tunnel_manager module (non-GUI logic)."""

from unittest.mock import patch, MagicMock

from fedoraxterm.tunnel_manager import SSHTunnel, TunnelManager


class TestSSHTunnel:
    """Tests for the SSHTunnel dataclass."""

    def test_local_tunnel_command(self):
        t = SSHTunnel(
            name="web",
            tunnel_type="local",
            local_port=8080,
            remote_host="127.0.0.1",
            remote_port=80,
            ssh_host="bastion.example.com",
            ssh_user="admin",
        )
        cmd = t.build_command()
        assert cmd[0] == "ssh"
        assert "-N" in cmd
        assert "-L" in cmd
        assert "8080:127.0.0.1:80" in cmd
        assert "admin@bastion.example.com" in cmd

    def test_remote_tunnel_command(self):
        t = SSHTunnel(
            name="reverse",
            tunnel_type="remote",
            local_port=3306,
            remote_host="db.internal",
            remote_port=3306,
            ssh_host="jump.example.com",
        )
        cmd = t.build_command()
        assert "-R" in cmd
        assert "3306:db.internal:3306" in cmd

    def test_custom_port(self):
        t = SSHTunnel(
            name="t", tunnel_type="local",
            local_port=1234, remote_port=5678,
            ssh_host="host", ssh_port=2222,
        )
        cmd = t.build_command()
        assert "-p" in cmd
        assert "2222" in cmd

    def test_default_port_no_flag(self):
        t = SSHTunnel(
            name="t", tunnel_type="local",
            local_port=1234, remote_port=5678,
            ssh_host="host", ssh_port=22,
        )
        cmd = t.build_command()
        assert "-p" not in cmd

    def test_with_key(self):
        t = SSHTunnel(
            name="t", tunnel_type="local",
            local_port=1234, remote_port=5678,
            ssh_host="host", private_key_path="/path/key",
        )
        cmd = t.build_command()
        assert "-i" in cmd
        assert "/path/key" in cmd

    def test_display_label(self):
        t = SSHTunnel(
            name="web",
            tunnel_type="local",
            local_port=8080,
            remote_host="127.0.0.1",
            remote_port=80,
            ssh_host="bastion",
        )
        label = t.display_label()
        assert "web" in label
        assert "8080" in label
        assert "80" in label
        assert "bastion" in label
        assert "→" in label  # local tunnel uses right arrow

    def test_display_label_remote(self):
        t = SSHTunnel(name="rev", tunnel_type="remote",
                      local_port=1, remote_port=2, ssh_host="h")
        assert "←" in t.display_label()


class TestTunnelManager:
    """Tests for TunnelManager."""

    def test_add_and_list(self):
        mgr = TunnelManager()
        t = SSHTunnel(name="t1", tunnel_type="local",
                      local_port=1, remote_port=2, ssh_host="h")
        mgr.add(t)
        assert len(mgr.tunnels) == 1

    def test_remove(self):
        mgr = TunnelManager()
        mgr.add(SSHTunnel(name="a", tunnel_type="local",
                          local_port=1, remote_port=2, ssh_host="h"))
        mgr.add(SSHTunnel(name="b", tunnel_type="local",
                          local_port=3, remote_port=4, ssh_host="h"))
        mgr.remove("a")
        assert len(mgr.tunnels) == 1
        assert mgr.tunnels[0].name == "b"

    def test_is_running_false_by_default(self):
        mgr = TunnelManager()
        assert mgr.is_running("anything") is False

    @patch("fedoraxterm.tunnel_manager.subprocess.Popen")
    def test_start_and_is_running(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        mock_popen.return_value = mock_proc

        mgr = TunnelManager()
        mgr.add(SSHTunnel(name="t", tunnel_type="local",
                          local_port=1, remote_port=2, ssh_host="h"))
        err = mgr.start("t")
        assert err is None
        assert mgr.is_running("t") is True

    def test_start_nonexistent(self):
        mgr = TunnelManager()
        err = mgr.start("nope")
        assert err is not None
        assert "not found" in err

    @patch("fedoraxterm.tunnel_manager.subprocess.Popen")
    def test_start_already_running(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        mgr = TunnelManager()
        mgr.add(SSHTunnel(name="t", tunnel_type="local",
                          local_port=1, remote_port=2, ssh_host="h"))
        mgr.start("t")
        err = mgr.start("t")
        assert err is not None
        assert "already running" in err

    @patch("fedoraxterm.tunnel_manager.subprocess.Popen")
    def test_stop(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        mgr = TunnelManager()
        mgr.add(SSHTunnel(name="t", tunnel_type="local",
                          local_port=1, remote_port=2, ssh_host="h"))
        mgr.start("t")
        mgr.stop("t")
        mock_proc.terminate.assert_called_once()
        assert mgr.is_running("t") is False
