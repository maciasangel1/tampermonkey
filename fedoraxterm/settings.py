"""Settings management for FedoraXTerm.

Provides dataclass-based configuration with JSON persistence and
XDG-compliant storage paths.  Modelled after SecureCRT's session /
global-options hierarchy so that power-users feel at home.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── XDG helpers ─────────────────────────────────────────────────────

_APP_NAME = "fedoraxterm"


def _xdg_config_home() -> Path:
    """Return ``$XDG_CONFIG_HOME`` or fall back to ``~/.config``."""
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def _default_config_dir() -> Path:
    return _xdg_config_home() / _APP_NAME


def _default_download_dir() -> str:
    return str(Path.home() / "Downloads")


# ── Serialisation helpers ───────────────────────────────────────────


def dataclass_to_dict(obj: Any) -> dict[str, Any]:
    """Convert a dataclass instance to a plain *dict*.

    Delegates to :func:`dataclasses.asdict` which handles nested
    dataclasses, lists, and dicts recursively.
    """
    return asdict(obj)


def dict_to_dataclass(cls: type, data: dict[str, Any]) -> Any:
    """Merge *data* into a new instance of dataclass *cls*.

    Unknown keys are silently dropped and missing keys receive the
    default value defined on the dataclass – this makes config files
    written by older (or newer) versions forward-/backward-compatible.
    """
    defaults = cls()
    merged: dict[str, Any] = {}
    for f in cls.__dataclass_fields__:
        if f in data:
            merged[f] = data[f]
        else:
            merged[f] = getattr(defaults, f)
    return cls(**merged)


# ── Keyword highlighting ────────────────────────────────────────────


def _default_keyword() -> dict[str, Any]:
    """Schema reference for a single keyword-highlight entry."""
    return {
        "pattern": "",
        "color": "#ff0000",
        "bold": False,
        "whole_word": False,
        "case_sensitive": False,
        "is_regex": False,
    }


@dataclass
class KeywordHighlightSet:
    """A named collection of keyword-highlight rules.

    Each entry in *keywords* is a dict matching the schema returned by
    :func:`_default_keyword`.
    """

    name: str = "Default"
    keywords: list[dict[str, Any]] = field(default_factory=list)


# ── Button bar ──────────────────────────────────────────────────────


@dataclass
class ButtonBarConfig:
    """A named button-bar with a list of quick-command buttons.

    Each entry in *buttons* carries a label, the shell command to send,
    and optional display hints.
    """

    name: str = "Default"
    buttons: list[dict[str, Any]] = field(default_factory=list)

    # Convenience schema reference for a single button.
    @staticmethod
    def default_button() -> dict[str, Any]:
        """Return the default schema for a button entry."""
        return {
            "label": "",
            "command": "",
            "icon": "",
            "color": "",
            "send_to_all": False,
        }


# ── SSH / session dataclass ─────────────────────────────────────────


@dataclass
class SSHSession:
    """All per-session settings, mirroring SecureCRT's session options.

    Covers SSH, Telnet, serial, raw-socket, and rlogin protocols with
    their respective transport parameters.
    """

    # ── Connection ───────────────────────────────────────────────
    hostname: str = ""
    port: int = 22
    username: str = ""
    auth_method: str = "password"  # password | publickey | keyboard-interactive
    private_key_path: str = ""
    use_agent_forwarding: bool = False

    # ── Proxy / firewall ─────────────────────────────────────────
    firewall_type: str = "none"  # none | socks4 | socks5 | http
    firewall_host: str = ""
    firewall_port: int = 0
    firewall_user: str = ""

    # ── Jump host ────────────────────────────────────────────────
    jump_host: str = ""
    jump_port: int = 22
    jump_user: str = ""

    # ── Organisation / appearance ────────────────────────────────
    session_name: str = ""
    folder: str = ""
    color_scheme: str = ""
    description: str = ""

    # ── Logging ──────────────────────────────────────────────────
    log_to_file: bool = False
    log_filename: str = ""

    # ── Automation ───────────────────────────────────────────────
    auto_command: str = ""

    # ── Keep-alive ───────────────────────────────────────────────
    send_keepalive: bool = True
    keepalive_interval: int = 30

    # ── Forwarding / compression ─────────────────────────────────
    x11_forwarding: bool = False
    compression: bool = False

    # ── Protocol ─────────────────────────────────────────────────
    protocol: str = "ssh2"  # ssh2 | telnet | serial | raw | rlogin

    # ── Serial-specific ──────────────────────────────────────────
    serial_port: str = ""
    serial_baud: int = 9600
    serial_data_bits: int = 8
    serial_stop_bits: int = 1
    serial_parity: str = "none"  # none | odd | even | mark | space
    serial_flow_control: str = "none"  # none | xon_xoff | rts_cts | dtr_dsr

    # ── Telnet-specific ──────────────────────────────────────────
    telnet_terminal_type: str = "xterm"

    # ── Encoding ─────────────────────────────────────────────────
    encoding: str = "utf-8"

    # ── Keyword highlighting ─────────────────────────────────────
    keyword_highlight_set: str = ""


# ── Global application settings ─────────────────────────────────────


@dataclass
class AppSettings:
    """Global application settings (not per-session).

    Mirrors the breadth of SecureCRT's *Global Options* dialog –
    terminal behaviour, appearance, logging defaults, keyboard mapping,
    file-transfer paths, and miscellaneous UI preferences.
    """

    # ── Terminal ─────────────────────────────────────────────────
    font_family: str = "Monospace"
    font_size: int = 12
    scrollback_lines: int = 10000
    cursor_shape: str = "block"  # block | ibeam | underline
    cursor_blink: bool = True
    audible_bell: bool = True
    visual_bell: bool = False
    word_chars: str = "-A-Za-z0-9,./?%&#:_=+@~"
    scroll_on_output: bool = False
    scroll_on_keystroke: bool = True
    allow_bold: bool = True
    rewrap_on_resize: bool = True

    # ── Appearance ───────────────────────────────────────────────
    theme: str = "Default"
    opacity: float = 1.0
    show_toolbar: bool = True
    show_statusbar: bool = True
    show_menubar: bool = True
    show_sidebar: bool = True
    tab_position: str = "top"  # top | bottom | left | right
    window_width: int = 900
    window_height: int = 550
    use_system_font: bool = True

    # ── Logging ──────────────────────────────────────────────────
    log_sessions: bool = False
    log_directory: str = ""
    log_format: str = "plain"  # raw | html | plain
    log_append: bool = True
    log_timestamps: bool = True

    # ── Keyboard ─────────────────────────────────────────────────
    custom_keybindings: dict[str, str] = field(default_factory=dict)
    map_delete_to_backspace: bool = False
    alt_sends_escape: bool = True

    # ── Transfer ─────────────────────────────────────────────────
    default_download_dir: str = ""
    default_upload_dir: str = ""
    zmodem_auto_detect: bool = True

    # ── Misc / UI ────────────────────────────────────────────────
    confirm_close: bool = True
    close_on_disconnect: bool = False
    auto_reconnect: bool = False
    reconnect_delay: int = 5
    show_quick_connect: bool = True
    sidebar_width: int = 200
    sftp_panel_height: int = 200

    def __post_init__(self) -> None:
        if not self.default_download_dir:
            self.default_download_dir = _default_download_dir()
        if not self.default_upload_dir:
            self.default_upload_dir = _default_download_dir()


# ── Settings manager ────────────────────────────────────────────────

_SETTINGS_FILE = "settings.json"
_SESSIONS_DIR = "sessions"
_KEYWORD_SETS_DIR = "keyword_sets"
_BUTTON_BARS_DIR = "button_bars"


class SettingsManager:
    """Centralised read/write access to all persistent configuration.

    Directory layout under ``~/.config/fedoraxterm/``::

        settings.json            – global :class:`AppSettings`
        sessions/
            <folder>/<name>.json – per-session :class:`SSHSession` files
        keyword_sets/
            <name>.json          – :class:`KeywordHighlightSet` files
        button_bars/
            <name>.json          – :class:`ButtonBarConfig` files
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir: Path = config_dir or _default_config_dir()
        self.sessions_dir: Path = self.config_dir / _SESSIONS_DIR
        self.keyword_sets_dir: Path = self.config_dir / _KEYWORD_SETS_DIR
        self.button_bars_dir: Path = self.config_dir / _BUTTON_BARS_DIR
        self.settings: AppSettings = AppSettings()

    # ── Directory bootstrapping ──────────────────────────────────

    def _ensure_dirs(self) -> None:
        """Create the config directory tree if it does not exist."""
        for d in (
            self.config_dir,
            self.sessions_dir,
            self.keyword_sets_dir,
            self.button_bars_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    # ── Global settings ──────────────────────────────────────────

    def load(self) -> AppSettings:
        """Load global settings from disk, falling back to defaults.

        Returns the loaded (or default) :class:`AppSettings` instance,
        which is also stored on ``self.settings``.
        """
        self._ensure_dirs()
        path = self.config_dir / _SETTINGS_FILE
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.settings = dict_to_dataclass(AppSettings, data)
            except (json.JSONDecodeError, TypeError, KeyError):
                logger.warning(
                    "Corrupted settings file %s – falling back to defaults.",
                    path,
                )
                self.settings = AppSettings()
        else:
            self.settings = AppSettings()
        return self.settings

    def save(self) -> None:
        """Persist the current global settings to disk."""
        self._ensure_dirs()
        path = self.config_dir / _SETTINGS_FILE
        path.write_text(
            json.dumps(dataclass_to_dict(self.settings), indent=2) + "\n",
            encoding="utf-8",
        )

    # ── Session management ───────────────────────────────────────

    def _session_path(self, session: SSHSession) -> Path:
        """Derive the on-disk path for a session file."""
        folder = session.folder.strip("/") if session.folder else ""
        name = session.session_name or session.hostname or "unnamed"
        base = self.sessions_dir / folder if folder else self.sessions_dir
        return base / f"{name}.json"

    def load_sessions(self) -> list[SSHSession]:
        """Recursively load every session file under *sessions_dir*."""
        self._ensure_dirs()
        sessions: list[SSHSession] = []
        for path in sorted(self.sessions_dir.rglob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                sessions.append(dict_to_dataclass(SSHSession, data))
            except (json.JSONDecodeError, TypeError, KeyError):
                logger.warning("Skipping corrupted session file: %s", path)
        return sessions

    def save_session(self, session: SSHSession) -> Path:
        """Write a single session to disk and return its path."""
        self._ensure_dirs()
        path = self._session_path(session)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(dataclass_to_dict(session), indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def delete_session(self, session: SSHSession) -> bool:
        """Remove the session file from disk.  Returns *True* on success."""
        path = self._session_path(session)
        if path.is_file():
            path.unlink()
            # Remove empty parent folders up to sessions_dir.
            parent = path.parent
            while parent != self.sessions_dir:
                try:
                    parent.rmdir()  # only succeeds when empty
                except OSError:
                    break
                parent = parent.parent
            return True
        return False

    def export_sessions(self, dest: Path) -> None:
        """Export all sessions as a single JSON array to *dest*."""
        sessions = self.load_sessions()
        payload = [dataclass_to_dict(s) for s in sessions]
        dest.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )

    def import_sessions(self, src: Path) -> list[SSHSession]:
        """Import sessions from a JSON array file, saving each one.

        Returns the list of imported :class:`SSHSession` instances.
        """
        data = json.loads(src.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("Expected a JSON array of session objects.")
        imported: list[SSHSession] = []
        for entry in data:
            session = dict_to_dataclass(SSHSession, entry)
            self.save_session(session)
            imported.append(session)
        return imported

    def get_session_folders(self) -> dict[str, Any]:
        """Return the session folder hierarchy as a nested dict.

        Leaf entries are ``None``; branch entries are sub-dicts.

        Example::

            {"Servers": {"Production": None, "Staging": None}, "Routers": None}
        """
        self._ensure_dirs()
        tree: dict[str, Any] = {}
        for path in sorted(self.sessions_dir.rglob("*.json")):
            rel = path.relative_to(self.sessions_dir)
            parts = rel.parent.parts  # folder segments, excluding filename
            node = tree
            for part in parts:
                if part not in node:
                    node[part] = {}
                child = node[part]
                if not isinstance(child, dict):
                    node[part] = {}
                    child = node[part]
                node = child
        return tree

    # ── Keyword highlight sets ───────────────────────────────────

    def load_keyword_sets(self) -> list[KeywordHighlightSet]:
        """Load all keyword-highlight sets from disk."""
        self._ensure_dirs()
        sets: list[KeywordHighlightSet] = []
        for path in sorted(self.keyword_sets_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                sets.append(dict_to_dataclass(KeywordHighlightSet, data))
            except (json.JSONDecodeError, TypeError, KeyError):
                logger.warning(
                    "Skipping corrupted keyword-set file: %s", path,
                )
        return sets

    def save_keyword_set(self, kw_set: KeywordHighlightSet) -> Path:
        """Persist a keyword-highlight set to disk."""
        self._ensure_dirs()
        path = self.keyword_sets_dir / f"{kw_set.name}.json"
        path.write_text(
            json.dumps(dataclass_to_dict(kw_set), indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    # ── Button bars ──────────────────────────────────────────────

    def load_button_bars(self) -> list[ButtonBarConfig]:
        """Load all button-bar configurations from disk."""
        self._ensure_dirs()
        bars: list[ButtonBarConfig] = []
        for path in sorted(self.button_bars_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                bars.append(dict_to_dataclass(ButtonBarConfig, data))
            except (json.JSONDecodeError, TypeError, KeyError):
                logger.warning(
                    "Skipping corrupted button-bar file: %s", path,
                )
        return bars

    def save_button_bar(self, bar: ButtonBarConfig) -> Path:
        """Persist a button-bar configuration to disk."""
        self._ensure_dirs()
        path = self.button_bars_dir / f"{bar.name}.json"
        path.write_text(
            json.dumps(dataclass_to_dict(bar), indent=2) + "\n",
            encoding="utf-8",
        )
        return path
