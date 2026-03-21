"""Macro recording and playback engine for FedoRT.

Provides a :class:`MacroManager` that records terminal commands into
reusable :class:`Macro` objects, persists them to JSON, and plays them
back through an arbitrary *feed_callback* (typically
:pymethod:`TerminalWidget.feed_command`).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── Dataclass ────────────────────────────────────────────────────────


@dataclass
class Macro:
    """A recorded sequence of terminal commands.

    Attributes
    ----------
    name:
        Human-readable macro name (also used as lookup key).
    commands:
        Ordered list of command dicts, each containing *text* (the
        command string) and *delay* (seconds to wait before sending).
    created:
        ISO-8601 timestamp of when the macro was created.
    description:
        Optional user-supplied description.
    shortcut:
        Optional keyboard shortcut string (e.g. ``"<Ctrl><Shift>F5"``).
    """

    name: str
    commands: list[dict[str, object]] = field(default_factory=list)
    created: str = ""
    description: str = ""
    shortcut: str = ""

    def __post_init__(self) -> None:
        if not self.created:
            self.created = datetime.now(timezone.utc).isoformat()


# ── Manager ──────────────────────────────────────────────────────────


class MacroManager:
    """Record, store, and play back terminal macros.

    Parameters
    ----------
    macros:
        Optional pre-populated mapping of macro names to
        :class:`Macro` instances.
    """

    def __init__(self, macros: Optional[dict[str, Macro]] = None) -> None:
        self.macros: dict[str, Macro] = macros or {}
        self.is_recording: bool = False
        self._record_buffer: list[dict[str, object]] = []
        self._record_name: str = ""
        self._record_start: float = 0.0

    # ── Recording ────────────────────────────────────────────────

    def start_recording(self, name: str) -> None:
        """Begin recording a new macro called *name*.

        Parameters
        ----------
        name:
            Name for the macro being recorded.

        Raises
        ------
        RuntimeError
            If a recording is already in progress.
        """
        if self.is_recording:
            raise RuntimeError("A recording is already in progress.")
        self._record_name = name
        self._record_buffer = []
        self._record_start = time.monotonic()
        self.is_recording = True
        logger.info("Macro recording started: %s", name)

    def record_command(self, text: str) -> None:
        """Append a command to the current recording.

        The delay is calculated relative to the previous command (or to
        :meth:`start_recording` for the first command).

        Parameters
        ----------
        text:
            The command text to record.

        Raises
        ------
        RuntimeError
            If no recording is in progress.
        """
        if not self.is_recording:
            raise RuntimeError("No recording in progress.")
        now = time.monotonic()
        delay = now - self._record_start if not self._record_buffer else now - (
            self._record_start + sum(c["delay"] for c in self._record_buffer)
        )
        delay = max(0.0, delay)
        self._record_buffer.append({"text": text, "delay": round(delay, 4)})
        logger.debug("Recorded command (delay=%.4fs): %s", delay, text)

    def stop_recording(self) -> Macro:
        """Finish recording and return the new :class:`Macro`.

        The macro is automatically stored in :attr:`macros`.

        Returns
        -------
        Macro
            The newly created macro.

        Raises
        ------
        RuntimeError
            If no recording is in progress.
        """
        if not self.is_recording:
            raise RuntimeError("No recording in progress.")
        macro = Macro(
            name=self._record_name,
            commands=list(self._record_buffer),
        )
        self.macros[macro.name] = macro
        self.is_recording = False
        self._record_buffer = []
        self._record_name = ""
        self._record_start = 0.0
        logger.info("Macro recording stopped: %s (%d commands)",
                     macro.name, len(macro.commands))
        return macro

    # ── Playback ─────────────────────────────────────────────────

    def play_macro(
        self,
        name: str,
        feed_callback: Callable[[str], None],
    ) -> None:
        """Play a macro synchronously, blocking the calling thread.

        Each command is sent to *feed_callback* after sleeping for the
        recorded delay.

        Parameters
        ----------
        name:
            Name of the macro to play.
        feed_callback:
            Callable that accepts a command string and feeds it to the
            terminal (e.g. ``terminal.feed_command``).

        Raises
        ------
        KeyError
            If *name* does not match a stored macro.
        """
        macro = self._get_macro_or_raise(name)
        logger.info("Playing macro: %s", name)
        for cmd in macro.commands:
            delay: float = cmd.get("delay", 0.0)  # type: ignore[arg-type]
            if delay > 0:
                time.sleep(delay)
            feed_callback(cmd["text"])  # type: ignore[arg-type]

    def play_macro_async(
        self,
        name: str,
        feed_callback: Callable[[str], None],
    ) -> threading.Thread:
        """Play a macro asynchronously in a daemon thread.

        Parameters
        ----------
        name:
            Name of the macro to play.
        feed_callback:
            Callable that accepts a command string.

        Returns
        -------
        threading.Thread
            The started daemon thread performing playback.

        Raises
        ------
        KeyError
            If *name* does not match a stored macro.
        """
        self._get_macro_or_raise(name)
        thread = threading.Thread(
            target=self.play_macro,
            args=(name, feed_callback),
            daemon=True,
        )
        thread.start()
        return thread

    # ── Persistence ──────────────────────────────────────────────

    def save_macros(self, filepath: str) -> None:
        """Persist all macros to a JSON file.

        Parameters
        ----------
        filepath:
            Destination path for the JSON file.
        """
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        data = {name: asdict(macro) for name, macro in self.macros.items()}
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        logger.info("Saved %d macros to %s", len(self.macros), filepath)

    def load_macros(self, filepath: str) -> None:
        """Load macros from a JSON file, merging with existing macros.

        Parameters
        ----------
        filepath:
            Path to the JSON file previously saved by
            :meth:`save_macros`.

        Raises
        ------
        FileNotFoundError
            If *filepath* does not exist.
        """
        with open(filepath, "r", encoding="utf-8") as fh:
            data: dict[str, object] = json.load(fh)
        for name, mdict in data.items():
            self.macros[name] = Macro(**mdict)  # type: ignore[arg-type]
        logger.info("Loaded %d macros from %s", len(data), filepath)

    # ── CRUD ─────────────────────────────────────────────────────

    def delete_macro(self, name: str) -> None:
        """Delete a macro by name.

        Parameters
        ----------
        name:
            The macro to remove.

        Raises
        ------
        KeyError
            If *name* is not found.
        """
        self._get_macro_or_raise(name)
        del self.macros[name]
        logger.info("Deleted macro: %s", name)

    def rename_macro(self, old_name: str, new_name: str) -> None:
        """Rename an existing macro.

        Parameters
        ----------
        old_name:
            Current name.
        new_name:
            Desired new name.

        Raises
        ------
        KeyError
            If *old_name* does not exist.
        ValueError
            If *new_name* already exists.
        """
        macro = self._get_macro_or_raise(old_name)
        if new_name in self.macros:
            raise ValueError(f"Macro {new_name!r} already exists.")
        macro.name = new_name
        self.macros[new_name] = macro
        del self.macros[old_name]
        logger.info("Renamed macro %s → %s", old_name, new_name)

    def get_macro(self, name: str) -> Macro:
        """Return a macro by name.

        Parameters
        ----------
        name:
            Macro name.

        Returns
        -------
        Macro
            The requested macro.

        Raises
        ------
        KeyError
            If *name* is not found.
        """
        return self._get_macro_or_raise(name)

    def list_macros(self) -> list[str]:
        """Return a sorted list of all macro names.

        Returns
        -------
        list[str]
            Sorted macro names.
        """
        return sorted(self.macros.keys())

    # ── Import / Export ──────────────────────────────────────────

    def export_macro(self, name: str, filepath: str) -> None:
        """Export a single macro to a standalone JSON file.

        Parameters
        ----------
        name:
            Macro to export.
        filepath:
            Destination path.

        Raises
        ------
        KeyError
            If *name* is not found.
        """
        macro = self._get_macro_or_raise(name)
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(asdict(macro), fh, indent=2, ensure_ascii=False)
        logger.info("Exported macro %s to %s", name, filepath)

    def import_macro(self, filepath: str) -> Macro:
        """Import a macro from a JSON file.

        The macro is added to the internal store.  If a macro with the
        same name already exists it is overwritten.

        Parameters
        ----------
        filepath:
            Path to a JSON file containing a single macro.

        Returns
        -------
        Macro
            The imported macro.

        Raises
        ------
        FileNotFoundError
            If *filepath* does not exist.
        """
        with open(filepath, "r", encoding="utf-8") as fh:
            data: dict[str, object] = json.load(fh)
        macro = Macro(**data)  # type: ignore[arg-type]
        self.macros[macro.name] = macro
        logger.info("Imported macro %s from %s", macro.name, filepath)
        return macro

    # ── Helpers ──────────────────────────────────────────────────

    def _get_macro_or_raise(self, name: str) -> Macro:
        """Return the macro named *name* or raise :exc:`KeyError`."""
        try:
            return self.macros[name]
        except KeyError:
            raise KeyError(f"Macro {name!r} not found.") from None
