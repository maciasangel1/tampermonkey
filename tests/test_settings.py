"""Tests for fedoraxterm.settings module."""

import json
import tempfile
from pathlib import Path

from fedoraxterm.settings import AppSettings, SSHSession, SettingsManager


class TestAppSettings:
    """Tests for the AppSettings dataclass."""

    def test_defaults(self):
        s = AppSettings()
        assert s.window_width == 1200
        assert s.window_height == 800
        assert s.font_family == "Monospace"
        assert s.font_size == 11
        assert s.scrollback_lines == 10000
        assert s.show_sidebar is True
        assert s.confirm_close_tab is True

    def test_custom_values(self):
        s = AppSettings(font_size=14, show_sidebar=False)
        assert s.font_size == 14
        assert s.show_sidebar is False


class TestSSHSession:
    """Tests for the SSHSession dataclass."""

    def test_defaults(self):
        s = SSHSession(name="test", host="example.com")
        assert s.port == 22
        assert s.username == ""
        assert s.auth_method == "password"
        assert s.folder == "Default"

    def test_display_label(self):
        s = SSHSession(name="web", host="10.0.0.1", username="admin", port=2222)
        label = s.display_label()
        assert "web" in label
        assert "admin@" in label
        assert "10.0.0.1" in label
        assert ":2222" in label

    def test_display_label_default_port(self):
        s = SSHSession(name="db", host="db.local", username="root")
        label = s.display_label()
        assert ":22" not in label  # default port is hidden

    def test_display_label_no_user(self):
        s = SSHSession(name="gw", host="gateway.local")
        label = s.display_label()
        assert "@" not in label


class TestSettingsManager:
    """Tests for SettingsManager persistence."""

    def test_save_and_load_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SettingsManager(config_dir=Path(tmpdir))
            mgr.settings.font_size = 16
            mgr.settings.show_sidebar = False
            mgr.save()

            mgr2 = SettingsManager(config_dir=Path(tmpdir))
            mgr2.load()
            assert mgr2.settings.font_size == 16
            assert mgr2.settings.show_sidebar is False

    def test_save_and_load_sessions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SettingsManager(config_dir=Path(tmpdir))
            mgr.add_session(
                SSHSession(name="s1", host="h1", username="u1", port=22)
            )
            mgr.add_session(
                SSHSession(name="s2", host="h2", username="u2", port=2222)
            )

            mgr2 = SettingsManager(config_dir=Path(tmpdir))
            mgr2.load()
            assert len(mgr2.sessions) == 2
            assert mgr2.sessions[0].name == "s1"
            assert mgr2.sessions[1].port == 2222

    def test_remove_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SettingsManager(config_dir=Path(tmpdir))
            mgr.add_session(SSHSession(name="a", host="a.com"))
            mgr.add_session(SSHSession(name="b", host="b.com"))
            mgr.remove_session("a")
            assert len(mgr.sessions) == 1
            assert mgr.sessions[0].name == "b"

    def test_get_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SettingsManager(config_dir=Path(tmpdir))
            mgr.add_session(SSHSession(name="find_me", host="x.com"))
            found = mgr.get_session("find_me")
            assert found is not None
            assert found.host == "x.com"
            assert mgr.get_session("nonexistent") is None

    def test_get_folders(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SettingsManager(config_dir=Path(tmpdir))
            mgr.add_session(SSHSession(name="a", host="a", folder="Prod"))
            mgr.add_session(SSHSession(name="b", host="b", folder="Dev"))
            mgr.add_session(SSHSession(name="c", host="c", folder="Prod"))
            folders = mgr.get_folders()
            assert folders == ["Dev", "Prod"]

    def test_load_corrupted_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "settings.json").write_text("not valid json")
            mgr = SettingsManager(config_dir=Path(tmpdir))
            mgr.load()
            # Should fall back to defaults
            assert mgr.settings.font_size == 11

    def test_load_corrupted_sessions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "sessions.json").write_text("{bad json")
            mgr = SettingsManager(config_dir=Path(tmpdir))
            mgr.load()
            assert mgr.sessions == []
