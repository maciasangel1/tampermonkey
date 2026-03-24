"""Application settings and session persistence for FedoraXTerm."""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


def _config_dir() -> Path:
    """Return the XDG-compliant configuration directory."""
    xdg = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    path = Path(xdg) / "fedoraxterm"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _data_dir() -> Path:
    """Return the XDG-compliant data directory."""
    xdg = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    path = Path(xdg) / "fedoraxterm"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class SSHSession:
    """Represents a saved SSH session configuration."""

    name: str
    host: str
    port: int = 22
    username: str = ""
    password: str = ""
    auth_method: str = "password"  # "password" or "key"
    private_key_path: str = ""
    folder: str = "Default"

    def display_label(self) -> str:
        """Return a human-readable label for the session."""
        user_part = f"{self.username}@" if self.username else ""
        port_part = f":{self.port}" if self.port != 22 else ""
        return f"{self.name} ({user_part}{self.host}{port_part})"


@dataclass
class AppSettings:
    """Application-wide settings."""

    window_width: int = 1200
    window_height: int = 800
    font_family: str = "Monospace"
    font_size: int = 11
    scrollback_lines: int = 10000
    show_sidebar: bool = True
    confirm_close_tab: bool = True
    terminal_bg_color: str = "#1e1e2e"
    terminal_fg_color: str = "#cdd6f4"
    cursor_style: str = "block"        # "block", "ibeam", "underline"
    cursor_blink: bool = True
    tab_position: str = "top"          # "left", "top", "bottom", "right"
    terminal_bell: bool = True
    bold_is_bright: bool = True
    copy_on_select: bool = False
    theme: str = "Catppuccin Mocha"    # terminal colour theme name


class SettingsManager:
    """Manages loading and saving application settings and sessions."""

    def __init__(self, config_dir: Optional[Path] = None):
        self._config_dir = config_dir or _config_dir()
        self._settings_file = self._config_dir / "settings.json"
        self._sessions_file = self._config_dir / "sessions.json"
        self.settings = AppSettings()
        self.sessions: list[SSHSession] = []

    def load(self):
        """Load settings and sessions from disk."""
        self._load_settings()
        self._load_sessions()

    def save(self):
        """Persist settings and sessions to disk."""
        self._save_settings()
        self._save_sessions()

    # -- Settings ---------------------------------------------------------

    def _load_settings(self):
        """Load application settings from the JSON file."""
        if self._settings_file.exists():
            try:
                with open(self._settings_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self.settings = AppSettings(**{
                    k: v
                    for k, v in data.items()
                    if k in AppSettings.__dataclass_fields__
                })
            except (json.JSONDecodeError, TypeError, KeyError):
                self.settings = AppSettings()

    def _save_settings(self):
        """Save application settings to the JSON file."""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        with open(self._settings_file, "w", encoding="utf-8") as fh:
            json.dump(asdict(self.settings), fh, indent=2)

    # -- Sessions ---------------------------------------------------------

    def _load_sessions(self):
        """Load saved SSH sessions from the JSON file."""
        if self._sessions_file.exists():
            try:
                with open(self._sessions_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self.sessions = [
                    SSHSession(**{
                        k: v
                        for k, v in s.items()
                        if k in SSHSession.__dataclass_fields__
                    })
                    for s in data
                ]
            except (json.JSONDecodeError, TypeError, KeyError):
                self.sessions = []

    def _save_sessions(self):
        """Save SSH sessions to the JSON file."""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        with open(self._sessions_file, "w", encoding="utf-8") as fh:
            json.dump([asdict(s) for s in self.sessions], fh, indent=2)

    def add_session(self, session: SSHSession):
        """Add a new session and persist."""
        self.sessions.append(session)
        self._save_sessions()

    def update_session(self, name: str, **kwargs):
        """Update fields on an existing session by name and persist."""
        session = self.get_session(name)
        if session is None:
            return
        for key, value in kwargs.items():
            if hasattr(session, key):
                setattr(session, key, value)
        self._save_sessions()

    def remove_session(self, name: str):
        """Remove a session by name and persist."""
        self.sessions = [s for s in self.sessions if s.name != name]
        self._save_sessions()

    def get_session(self, name: str) -> Optional[SSHSession]:
        """Look up a session by name."""
        for s in self.sessions:
            if s.name == name:
                return s
        return None

    def get_folders(self) -> list[str]:
        """Return a sorted list of unique session folder names."""
        folders = {s.folder for s in self.sessions}
        return sorted(folders)
