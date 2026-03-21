"""Custom key mapping system for terminal emulator keybindings."""
from __future__ import annotations

import json
import os
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

# Optional GTK import for key-event parsing
try:
    import gi

    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk

    _GDK_AVAILABLE = True
except (ImportError, ValueError):
    Gdk = None  # type: ignore[assignment]
    _GDK_AVAILABLE = False


@dataclass
class KeyMapping:
    """A single key-to-action mapping.

    Attributes:
        key: Human-readable key combo, e.g. ``"Ctrl+Shift+A"`` or ``"F1"``.
        action_type: One of ``send_string``, ``run_command``, ``menu_action``,
            or ``macro``.
        action_value: The string to send, command to run, or menu action name.
        description: Optional description of what this mapping does.
        enabled: Whether the mapping is active.
    """

    key: str
    action_type: str
    action_value: str
    description: str = ""
    enabled: bool = True


# SecureCRT-like default keybindings
_DEFAULT_MAPPINGS: list[dict] = [
    {"key": "Alt+Return", "action_type": "menu_action", "action_value": "toggle_fullscreen", "description": "Toggle fullscreen"},
    {"key": "Ctrl+Shift+T", "action_type": "menu_action", "action_value": "new_tab", "description": "New tab"},
    {"key": "Ctrl+Shift+W", "action_type": "menu_action", "action_value": "close_tab", "description": "Close tab"},
    {"key": "Ctrl+Shift+C", "action_type": "menu_action", "action_value": "copy", "description": "Copy"},
    {"key": "Ctrl+Shift+V", "action_type": "menu_action", "action_value": "paste", "description": "Paste"},
    {"key": "Ctrl+Shift+F", "action_type": "menu_action", "action_value": "find", "description": "Find"},
    {"key": "Ctrl+Tab", "action_type": "menu_action", "action_value": "next_tab", "description": "Next tab"},
    {"key": "Ctrl+Shift+Tab", "action_type": "menu_action", "action_value": "previous_tab", "description": "Previous tab"},
    {"key": "F1", "action_type": "menu_action", "action_value": "help", "description": "Help"},
    {"key": "Ctrl+Shift+N", "action_type": "menu_action", "action_value": "new_ssh_session", "description": "New SSH session"},
    {"key": "Ctrl+Shift+U", "action_type": "menu_action", "action_value": "quick_connect", "description": "Quick connect"},
    {"key": "Ctrl+Shift+L", "action_type": "menu_action", "action_value": "toggle_logging", "description": "Toggle logging"},
    {"key": "Ctrl+Shift+M", "action_type": "menu_action", "action_value": "toggle_macro_recording", "description": "Toggle macro recording"},
    {"key": "Shift+Insert", "action_type": "menu_action", "action_value": "paste", "description": "Paste"},
]


class KeyMappingManager:
    """Manages key-to-action mappings with persistence and import/export.

    Provides SecureCRT-like default keybindings and supports custom overrides
    that can be saved/loaded from JSON files.
    """

    def __init__(self) -> None:
        self.mappings: list[KeyMapping] = []
        self.default_mappings: dict[str, KeyMapping] = {}
        self._init_defaults()

    # -- initialisation -------------------------------------------------------

    def _init_defaults(self) -> None:
        """Populate default_mappings from the module-level definition."""
        for entry in _DEFAULT_MAPPINGS:
            km = KeyMapping(**entry)
            self.default_mappings[km.key] = km
        self.reset_to_defaults()

    # -- CRUD -----------------------------------------------------------------

    def add_mapping(self, mapping: KeyMapping) -> None:
        """Add a new key mapping, replacing any existing mapping for the same key."""
        self.remove_mapping(mapping.key)
        self.mappings.append(mapping)
        logger.debug("Added mapping: %s -> %s", mapping.key, mapping.action_value)

    def remove_mapping(self, key: str) -> None:
        """Remove a mapping by its key combo string."""
        self.mappings = [m for m in self.mappings if m.key != key]

    def update_mapping(self, key: str, mapping: KeyMapping) -> None:
        """Update an existing mapping identified by *key*."""
        self.remove_mapping(key)
        self.mappings.append(mapping)

    def get_mapping(self, key: str) -> Optional[KeyMapping]:
        """Return the mapping for *key*, or ``None``."""
        for m in self.mappings:
            if m.key == key:
                return m
        return None

    def get_action(self, key_event: str) -> Optional[tuple[str, str]]:
        """Return ``(action_type, action_value)`` for a key event string.

        Args:
            key_event: A normalised key string such as ``"Ctrl+Shift+C"``.

        Returns:
            A tuple of *(action_type, action_value)* if a matching enabled
            mapping exists, otherwise ``None``.
        """
        mapping = self.get_mapping(key_event)
        if mapping and mapping.enabled:
            return (mapping.action_type, mapping.action_value)
        return None

    def list_mappings(self) -> list[KeyMapping]:
        """Return all current mappings."""
        return list(self.mappings)

    # -- key-event parsing ----------------------------------------------------

    @staticmethod
    def parse_key_event(event) -> str:  # noqa: ANN001  (Gdk.EventKey when available)
        """Convert a Gdk key event to a human-readable string like ``"Ctrl+Shift+A"``.

        Args:
            event: A ``Gdk.EventKey`` instance.

        Returns:
            A normalised key-combo string.

        Raises:
            RuntimeError: If GTK/Gdk is not available.
        """
        if not _GDK_AVAILABLE:
            raise RuntimeError(
                "Gdk is not available; cannot parse key events without GTK"
            )

        parts: list[str] = []
        state = event.state

        if state & Gdk.ModifierType.CONTROL_MASK:
            parts.append("Ctrl")
        if state & Gdk.ModifierType.MOD1_MASK:
            parts.append("Alt")
        if state & Gdk.ModifierType.SHIFT_MASK:
            parts.append("Shift")

        keyval = event.keyval
        key_name = Gdk.keyval_name(keyval)
        if key_name:
            # Normalise common names
            key_name = key_name.replace("_L", "").replace("_R", "")
            # Skip modifier-only keys
            if key_name not in {"Control", "Alt", "Shift", "Meta", "Super", "Hyper"}:
                parts.append(key_name.capitalize() if len(key_name) == 1 else key_name)

        return "+".join(parts)

    # -- persistence ----------------------------------------------------------

    def save(self, filepath: str) -> None:
        """Save all mappings to a JSON file.

        Args:
            filepath: Destination path for the JSON file.
        """
        data = [asdict(m) for m in self.mappings]
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        logger.info("Saved %d mappings to %s", len(data), filepath)

    def load(self, filepath: str) -> None:
        """Load mappings from a JSON file, replacing current mappings.

        Args:
            filepath: Path to the JSON file.
        """
        with open(filepath, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.mappings = [KeyMapping(**entry) for entry in data]
        logger.info("Loaded %d mappings from %s", len(self.mappings), filepath)

    # -- import / export ------------------------------------------------------

    def export_mappings(self, filepath: str) -> None:
        """Export current mappings to a JSON file (alias for :meth:`save`).

        Args:
            filepath: Destination path for the export file.
        """
        self.save(filepath)

    def import_mappings(self, filepath: str) -> None:
        """Import mappings from a JSON file, merging with current mappings.

        Existing mappings for the same key are replaced.

        Args:
            filepath: Path to the JSON file to import.
        """
        with open(filepath, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for entry in data:
            km = KeyMapping(**entry)
            self.add_mapping(km)
        logger.info("Imported mappings from %s", filepath)

    # -- reset ----------------------------------------------------------------

    def reset_to_defaults(self) -> None:
        """Replace all mappings with the built-in defaults."""
        self.mappings = [
            KeyMapping(
                key=km.key,
                action_type=km.action_type,
                action_value=km.action_value,
                description=km.description,
                enabled=km.enabled,
            )
            for km in self.default_mappings.values()
        ]
        logger.debug("Reset to %d default mappings", len(self.mappings))
