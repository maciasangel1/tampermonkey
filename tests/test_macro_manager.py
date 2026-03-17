"""Tests for fedoraxterm.macro_manager module (non-GUI logic)."""

import tempfile
from pathlib import Path

from fedoraxterm.macro_manager import Macro, MacroManager


class TestMacro:
    """Tests for the Macro dataclass."""

    def test_defaults(self):
        m = Macro(name="test")
        assert m.commands == []
        assert m.delay_ms == 200


class TestMacroManager:
    """Tests for MacroManager persistence and recording."""

    def _make_manager(self, tmpdir: str) -> MacroManager:
        return MacroManager(data_dir=Path(tmpdir))

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = self._make_manager(tmpdir)
            mgr.macros.append(Macro(name="m1", commands=["ls", "pwd"]))
            mgr.save()

            mgr2 = self._make_manager(tmpdir)
            assert len(mgr2.macros) == 1
            assert mgr2.macros[0].name == "m1"
            assert mgr2.macros[0].commands == ["ls", "pwd"]

    def test_recording(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = self._make_manager(tmpdir)
            assert mgr.is_recording is False

            mgr.start_recording("rec1")
            assert mgr.is_recording is True

            mgr.record_command("cd /tmp")
            mgr.record_command("ls -la")

            macro = mgr.stop_recording()
            assert mgr.is_recording is False
            assert macro is not None
            assert macro.name == "rec1"
            assert macro.commands == ["cd /tmp", "ls -la"]
            assert len(mgr.macros) == 1

    def test_recording_empty_discarded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = self._make_manager(tmpdir)
            mgr.start_recording("empty")
            macro = mgr.stop_recording()
            assert macro is None or macro.commands == []
            # Empty macros are not persisted
            mgr2 = self._make_manager(tmpdir)
            assert len(mgr2.macros) == 0

    def test_record_command_when_not_recording(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = self._make_manager(tmpdir)
            mgr.record_command("should be ignored")
            assert len(mgr.macros) == 0

    def test_delete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = self._make_manager(tmpdir)
            mgr.macros.append(Macro(name="a", commands=["x"]))
            mgr.macros.append(Macro(name="b", commands=["y"]))
            mgr.save()

            mgr.delete("a")
            assert len(mgr.macros) == 1
            assert mgr.macros[0].name == "b"

            # Verify it's persisted
            mgr2 = self._make_manager(tmpdir)
            assert len(mgr2.macros) == 1

    def test_corrupted_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "macros.json").write_text("not json")
            mgr = self._make_manager(tmpdir)
            assert mgr.macros == []
