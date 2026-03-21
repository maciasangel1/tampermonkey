"""Tests for fedoraxterm.window module.

These tests validate the non-GUI logic in window.py – theme presets,
tab-position mapping, CSS loading, and the helper structures.  GTK
widget creation is tested where possible using mocks or skipped when a
display server is not available.
"""

from __future__ import annotations

import importlib
import os
import sys
import unittest


class TestThemePresets(unittest.TestCase):
    """Validate the ``_THEME_PRESETS`` dictionary."""

    @classmethod
    def setUpClass(cls) -> None:
        # Allow import even without a display by faking DISPLAY.
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            os.environ["DISPLAY"] = ":99"
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            gi.require_version("Vte", "2.91")
            from fedoraxterm.window import _THEME_PRESETS, _TAB_POS_MAP, _APP_CSS
            cls._THEME_PRESETS = _THEME_PRESETS
            cls._TAB_POS_MAP = _TAB_POS_MAP
            cls._APP_CSS = _APP_CSS
            cls._available = True
        except (ImportError, ValueError):
            cls._available = False

    def test_theme_presets_not_empty(self) -> None:
        if not self._available:
            self.skipTest("GTK/VTE not available")
        self.assertGreater(len(self._THEME_PRESETS), 0)

    def test_default_theme_exists(self) -> None:
        if not self._available:
            self.skipTest("GTK/VTE not available")
        self.assertIn("Default", self._THEME_PRESETS)

    def test_all_themes_have_required_keys(self) -> None:
        if not self._available:
            self.skipTest("GTK/VTE not available")
        for name, theme in self._THEME_PRESETS.items():
            with self.subTest(theme=name):
                self.assertIn("fg", theme)
                self.assertIn("bg", theme)
                self.assertIn("palette", theme)
                self.assertIsInstance(theme["palette"], list)
                self.assertEqual(len(theme["palette"]), 16, f"{name} palette must have 16 colours")

    def test_theme_colour_format(self) -> None:
        if not self._available:
            self.skipTest("GTK/VTE not available")
        import re
        hex_re = re.compile(r"^#[0-9a-fA-F]{6}$")
        for name, theme in self._THEME_PRESETS.items():
            with self.subTest(theme=name, field="fg"):
                self.assertRegex(theme["fg"], hex_re)
            with self.subTest(theme=name, field="bg"):
                self.assertRegex(theme["bg"], hex_re)
            for idx, colour in enumerate(theme["palette"]):
                with self.subTest(theme=name, palette_idx=idx):
                    self.assertRegex(colour, hex_re)

    def test_seven_theme_presets(self) -> None:
        if not self._available:
            self.skipTest("GTK/VTE not available")
        # Expect exactly 8 presets: Default + 7 named themes.
        self.assertEqual(len(self._THEME_PRESETS), 8)

    def test_known_theme_names(self) -> None:
        if not self._available:
            self.skipTest("GTK/VTE not available")
        expected = {
            "Default", "Catppuccin Mocha", "Solarized Dark", "Dracula",
            "Nord", "Gruvbox Dark", "One Dark", "Tango",
        }
        self.assertEqual(set(self._THEME_PRESETS.keys()), expected)


class TestTabPositionMap(unittest.TestCase):
    """Validate ``_TAB_POS_MAP``."""

    @classmethod
    def setUpClass(cls) -> None:
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            os.environ["DISPLAY"] = ":99"
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            gi.require_version("Vte", "2.91")
            from fedoraxterm.window import _TAB_POS_MAP
            cls._TAB_POS_MAP = _TAB_POS_MAP
            cls._available = True
        except (ImportError, ValueError):
            cls._available = False

    def test_tab_position_keys(self) -> None:
        if not self._available:
            self.skipTest("GTK/VTE not available")
        self.assertEqual(set(self._TAB_POS_MAP.keys()), {"top", "bottom", "left", "right"})


class TestAppCSS(unittest.TestCase):
    """Validate that the application CSS string is valid."""

    @classmethod
    def setUpClass(cls) -> None:
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            os.environ["DISPLAY"] = ":99"
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            gi.require_version("Vte", "2.91")
            from fedoraxterm.window import _APP_CSS
            cls._APP_CSS = _APP_CSS
            cls._available = True
        except (ImportError, ValueError):
            cls._available = False

    def test_css_not_empty(self) -> None:
        if not self._available:
            self.skipTest("GTK/VTE not available")
        self.assertGreater(len(self._APP_CSS), 100)

    def test_css_no_transition_all(self) -> None:
        """GTK3 CSS ``transition: all`` can cause segfaults."""
        if not self._available:
            self.skipTest("GTK/VTE not available")
        self.assertNotIn("transition: all", self._APP_CSS)

    def test_css_no_box_shadow_inset(self) -> None:
        """GTK3 CSS ``box-shadow: inset`` can cause segfaults."""
        if not self._available:
            self.skipTest("GTK/VTE not available")
        self.assertNotIn("box-shadow: inset", self._APP_CSS)


class TestTabLabelConstants(unittest.TestCase):
    """Validate tab-label sizing constants."""

    @classmethod
    def setUpClass(cls) -> None:
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            os.environ["DISPLAY"] = ":99"
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            gi.require_version("Vte", "2.91")
            from fedoraxterm.window import _TAB_LABEL_MIN_CHARS, _TAB_LABEL_MAX_CHARS
            cls._min = _TAB_LABEL_MIN_CHARS
            cls._max = _TAB_LABEL_MAX_CHARS
            cls._available = True
        except (ImportError, ValueError):
            cls._available = False

    def test_min_less_than_max(self) -> None:
        if not self._available:
            self.skipTest("GTK/VTE not available")
        self.assertLess(self._min, self._max)

    def test_min_chars_value(self) -> None:
        if not self._available:
            self.skipTest("GTK/VTE not available")
        self.assertEqual(self._min, 8)

    def test_max_chars_value(self) -> None:
        if not self._available:
            self.skipTest("GTK/VTE not available")
        self.assertEqual(self._max, 20)


class TestModuleImport(unittest.TestCase):
    """Verify that the window module can be imported without errors."""

    def test_import_window(self) -> None:
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            os.environ["DISPLAY"] = ":99"
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            gi.require_version("Vte", "2.91")
        except (ImportError, ValueError):
            self.skipTest("GTK/VTE not available")
        import fedoraxterm.window
        self.assertTrue(hasattr(fedoraxterm.window, "MainWindow"))

    def test_import_app(self) -> None:
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            os.environ["DISPLAY"] = ":99"
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            gi.require_version("Vte", "2.91")
        except (ImportError, ValueError):
            self.skipTest("GTK/VTE not available")
        import fedoraxterm.app
        self.assertTrue(hasattr(fedoraxterm.app, "FedoraXTermApp"))
        self.assertTrue(hasattr(fedoraxterm.app, "MainWindow"))


if __name__ == "__main__":
    unittest.main()
