"""Session logging for FedoRT.

Provides :class:`SessionLogger` for writing terminal output to log
files in plain-text, HTML, or CSV format, and :class:`LogManager` for
coordinating per-tab loggers – mirroring SecureCRT's session-logging
feature with daily-rotation support.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import time
from pathlib import Path
from typing import Optional, TextIO

logger = logging.getLogger(__name__)

# ── ANSI → HTML helpers ─────────────────────────────────────────────

_ANSI_COLORS: dict[int, str] = {
    30: "#000000", 31: "#cc0000", 32: "#4e9a06", 33: "#c4a000",
    34: "#3465a4", 35: "#75507b", 36: "#06989a", 37: "#d3d7cf",
    90: "#555753", 91: "#ef2929", 92: "#8ae234", 93: "#fce94f",
    94: "#729fcf", 95: "#ad7fa8", 96: "#34e2e2", 97: "#eeeeec",
}

_HTML_HEADER = (
    "<!DOCTYPE html>\n<html><head><meta charset='utf-8'>"
    "<title>FedoRT Session Log</title>"
    "<style>body{background:#1e1e1e;color:#d0d0d0;"
    "font-family:monospace;white-space:pre-wrap;}</style>"
    "</head><body>\n"
)
_HTML_FOOTER = "</body></html>\n"


def _ansi_to_html(text: str) -> str:
    """Convert a subset of ANSI escape codes to HTML ``<span>`` tags.

    Handles SGR colour codes (30–37, 90–97) and reset (0).  All other
    escape sequences are stripped.
    """
    import html as _html
    import re

    result: list[str] = []
    span_open = False

    for segment in re.split(r"(\x1b\[[0-9;]*m)", text):
        if segment.startswith("\x1b["):
            codes = segment[2:-1]
            if codes in ("", "0"):
                if span_open:
                    result.append("</span>")
                    span_open = False
            else:
                for code_str in codes.split(";"):
                    code = int(code_str) if code_str.isdigit() else 0
                    color = _ANSI_COLORS.get(code)
                    if color:
                        if span_open:
                            result.append("</span>")
                        result.append(f'<span style="color:{color}">')
                        span_open = True
        else:
            result.append(_html.escape(segment))

    if span_open:
        result.append("</span>")
    return "".join(result)


# ── SessionLogger ────────────────────────────────────────────────────


class SessionLogger:
    """Write terminal data to a log file.

    Supports plain-text, HTML, and CSV output formats with optional
    timestamps on every line written via :meth:`write_line`.

    Parameters
    ----------
    filepath:
        Destination log file (set via :meth:`open`).
    fmt:
        Output format – ``plain``, ``html``, or ``csv``.
    """

    def __init__(self) -> None:
        self._filepath: str = ""
        self._format: str = "plain"
        self._timestamps: bool = False
        self._fh: Optional[TextIO] = None
        self._csv_writer: Optional[csv.writer] = None

    # ── Lifecycle ────────────────────────────────────────────────

    def open(
        self,
        filepath: str,
        fmt: str = "plain",
        append: bool = True,
        timestamps: bool = False,
    ) -> None:
        """Open a log file for writing.

        Parameters
        ----------
        filepath:
            Destination file path.
        fmt:
            ``plain``, ``html``, or ``csv``.
        append:
            Append to an existing file instead of overwriting.
        timestamps:
            Prefix each :meth:`write_line` call with a timestamp.

        Raises
        ------
        ValueError
            If *fmt* is not a recognised format.
        RuntimeError
            If a log file is already open.
        """
        if self._fh is not None:
            raise RuntimeError("Logger already open – call close() first.")

        fmt = fmt.lower()
        if fmt not in ("plain", "html", "csv"):
            raise ValueError(f"Unsupported format {fmt!r}.")

        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        mode = "a" if append else "w"
        self._fh = open(filepath, mode, encoding="utf-8")  # noqa: SIM115
        self._filepath = filepath
        self._format = fmt
        self._timestamps = timestamps

        if fmt == "html" and not append:
            self._fh.write(_HTML_HEADER)
        if fmt == "csv":
            self._csv_writer = csv.writer(self._fh)
            if not append:
                self._csv_writer.writerow(["timestamp", "data"])

        logger.info("Session log opened: %s (format=%s)", filepath, fmt)

    def close(self) -> None:
        """Flush and close the log file."""
        if self._fh is None:
            return
        if self._format == "html":
            self._fh.write(_HTML_FOOTER)
        self._fh.close()
        logger.info("Session log closed: %s", self._filepath)
        self._fh = None
        self._csv_writer = None

    # ── Writing ──────────────────────────────────────────────────

    def write(self, data: str) -> None:
        """Write raw terminal data to the log.

        Parameters
        ----------
        data:
            Text to write.  No newline is appended automatically.
        """
        if self._fh is None:
            return
        if self._format == "html":
            self._fh.write(_ansi_to_html(data))
        elif self._format == "csv":
            ts = time.strftime("%Y-%m-%dT%H:%M:%S")
            if self._csv_writer is not None:
                self._csv_writer.writerow([ts, data])
        else:
            self._fh.write(data)

    def write_line(self, line: str) -> None:
        """Write a single line, optionally prefixed with a timestamp.

        A trailing newline is appended automatically.
        """
        if self._fh is None:
            return
        prefix = ""
        if self._timestamps:
            prefix = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "

        if self._format == "html":
            self._fh.write(_ansi_to_html(prefix + line) + "<br>\n")
        elif self._format == "csv":
            ts = time.strftime("%Y-%m-%dT%H:%M:%S")
            if self._csv_writer is not None:
                self._csv_writer.writerow([ts, line])
        else:
            self._fh.write(prefix + line + "\n")

    # ── Status helpers ───────────────────────────────────────────

    def is_open(self) -> bool:
        """Return *True* if a log file is currently open."""
        return self._fh is not None

    def get_filepath(self) -> str:
        """Return the path to the currently-open log file."""
        return self._filepath

    def flush(self) -> None:
        """Flush pending writes to disk."""
        if self._fh is not None:
            self._fh.flush()

    def rotate(self) -> None:
        """Close the current file and open a new one for daily rotation.

        The new filename is derived from the original path with today's
        date appended before the extension.
        """
        if self._fh is None:
            return

        old_path = self._filepath
        fmt = self._format
        ts = self._timestamps

        self.close()

        base, ext = os.path.splitext(old_path)
        new_path = f"{base}_{time.strftime('%Y%m%d_%H%M%S')}{ext}"
        self.open(new_path, fmt=fmt, append=False, timestamps=ts)
        logger.info("Log rotated: %s → %s", old_path, new_path)


# ── LogManager ───────────────────────────────────────────────────────


class LogManager:
    """Coordinate per-tab session loggers.

    Tracks active :class:`SessionLogger` instances keyed by *tab_id*
    and provides convenience methods for the application layer.
    """

    def __init__(self, log_dir: Optional[str] = None) -> None:
        self._log_dir: str = log_dir or str(
            Path.home() / ".local" / "share" / "fedort" / "logs",
        )
        self.active_loggers: dict[str, SessionLogger] = {}

    # ── Per-tab control ──────────────────────────────────────────

    def start_logging(
        self,
        tab_id: str,
        filepath: Optional[str] = None,
        fmt: str = "plain",
        append: bool = True,
        timestamps: bool = False,
    ) -> None:
        """Begin logging for a tab.

        Parameters
        ----------
        tab_id:
            Unique identifier for the terminal tab.
        filepath:
            Destination log file.  When *None* a name is generated
            via :meth:`generate_log_filename`.
        fmt:
            Output format (``plain``, ``html``, ``csv``).
        append:
            Append to an existing file.
        timestamps:
            Prefix lines with a timestamp.
        """
        if tab_id in self.active_loggers:
            logger.warning("Logging already active for tab %s", tab_id)
            return

        if filepath is None:
            filepath = os.path.join(
                self._log_dir,
                self.generate_log_filename(tab_id),
            )

        sl = SessionLogger()
        sl.open(filepath, fmt=fmt, append=append, timestamps=timestamps)
        self.active_loggers[tab_id] = sl

    def stop_logging(self, tab_id: str) -> None:
        """Stop logging for a tab and close its log file."""
        sl = self.active_loggers.pop(tab_id, None)
        if sl is not None:
            sl.close()

    def log_data(self, tab_id: str, data: str) -> None:
        """Write *data* to the logger for *tab_id* (if active)."""
        sl = self.active_loggers.get(tab_id)
        if sl is not None:
            sl.write(data)

    def is_logging(self, tab_id: str) -> bool:
        """Return *True* if logging is active for *tab_id*."""
        return tab_id in self.active_loggers

    # ── Helpers ──────────────────────────────────────────────────

    def get_log_dir(self) -> str:
        """Return the base log directory path."""
        return self._log_dir

    @staticmethod
    def generate_log_filename(session_name: str) -> str:
        """Build a log filename with an embedded timestamp.

        Returns a string like ``session_name_20240315_143022.log``.
        """
        safe_name = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in session_name
        )
        ts = time.strftime("%Y%m%d_%H%M%S")
        return f"{safe_name}_{ts}.log"
