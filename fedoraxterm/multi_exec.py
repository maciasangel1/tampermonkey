"""Multi-execution broadcast bar for FedoraXTerm.

Provides :class:`MultiExecBar`, a GTK widget that sits at the bottom of
the terminal area and broadcasts typed commands to every open terminal
tab simultaneously.  Useful for executing the same command across
multiple SSH sessions at once (à la SecureCRT *Send Commands to All
Sessions*).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, GObject, Gtk  # noqa: E402

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────

_MAX_HISTORY = 200

# ── Widget ───────────────────────────────────────────────────────────


class MultiExecBar(Gtk.Box):
    """Horizontal broadcast bar for sending commands to all terminals.

    Emitted Signals
    ---------------
    send-command (str)
        Fired when the user presses *Enter* or clicks **Send**.  The
        parameter is the command text to feed to each terminal.
    broadcast-toggled (bool)
        Fired when the broadcast toggle is switched.  ``True`` means
        broadcasting is now enabled.

    The bar contains:

    * A ``"Send to all:"`` label
    * A :class:`Gtk.Entry` for typing commands
    * A **Send** button
    * A toggle button to enable / disable broadcasting
    * A *"Include current tab"* checkbox
    """

    __gsignals__ = {
        "send-command": (
            GObject.SignalFlags.RUN_LAST,
            None,
            (str,),
        ),
        "broadcast-toggled": (
            GObject.SignalFlags.RUN_LAST,
            None,
            (bool,),
        ),
    }

    def __init__(self) -> None:
        super().__init__(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
        )
        self.set_margin_start(4)
        self.set_margin_end(4)
        self.set_margin_top(2)
        self.set_margin_bottom(2)

        self._history: list[str] = []
        self._history_index: int = -1
        self._saved_entry: str = ""

        self._build_ui()

    # ── UI construction ──────────────────────────────────────────

    def _build_ui(self) -> None:
        """Construct the child widgets."""
        # Toggle button
        self._toggle = Gtk.ToggleButton(label="Broadcast")
        self._toggle.set_tooltip_text("Enable or disable broadcasting")
        self._toggle.connect("toggled", self._on_toggle)
        self.pack_start(self._toggle, False, False, 0)

        # Label
        label = Gtk.Label(label="Send to all:")
        self.pack_start(label, False, False, 0)

        # Entry
        self._entry = Gtk.Entry()
        self._entry.set_placeholder_text("Type a command…")
        self._entry.set_hexpand(True)
        self._entry.connect("activate", self._on_activate)
        self._entry.connect("key-press-event", self._on_key_press)
        self.pack_start(self._entry, True, True, 0)

        # Send button
        send_btn = Gtk.Button(label="Send")
        send_btn.set_tooltip_text("Send command to all terminals")
        send_btn.connect("clicked", self._on_send_clicked)
        self.pack_start(send_btn, False, False, 0)

        # Include-current-tab checkbox
        self._include_current = Gtk.CheckButton(label="Include current tab")
        self._include_current.set_active(True)
        self._include_current.set_tooltip_text(
            "When checked the active terminal also receives the command"
        )
        self.pack_start(self._include_current, False, False, 0)

        self._update_sensitivity()

    # ── Public API ───────────────────────────────────────────────

    @property
    def broadcasting(self) -> bool:
        """Whether broadcasting is currently enabled."""
        return self._toggle.get_active()

    @broadcasting.setter
    def broadcasting(self, value: bool) -> None:
        self._toggle.set_active(value)

    @property
    def include_current_tab(self) -> bool:
        """Whether the currently focused tab should receive commands."""
        return self._include_current.get_active()

    @include_current_tab.setter
    def include_current_tab(self, value: bool) -> None:
        self._include_current.set_active(value)

    def get_entry_text(self) -> str:
        """Return the current text in the command entry.

        Returns
        -------
        str
            The entry text.
        """
        return self._entry.get_text()

    def set_entry_text(self, text: str) -> None:
        """Set the command entry text.

        Parameters
        ----------
        text:
            New entry text.
        """
        self._entry.set_text(text)

    def focus_entry(self) -> None:
        """Move keyboard focus to the command entry."""
        self._entry.grab_focus()

    def get_history(self) -> list[str]:
        """Return a copy of the command history.

        Returns
        -------
        list[str]
            Previously sent commands, oldest first.
        """
        return list(self._history)

    def clear_history(self) -> None:
        """Clear the command history."""
        self._history.clear()
        self._history_index = -1

    # ── Signal handlers ──────────────────────────────────────────

    def _on_toggle(self, toggle: Gtk.ToggleButton) -> None:
        """Handle the broadcast toggle."""
        active = toggle.get_active()
        self._update_sensitivity()
        self.emit("broadcast-toggled", active)
        logger.debug("Broadcast toggled: %s", active)

    def _on_activate(self, _entry: Gtk.Entry) -> None:
        """Handle *Enter* in the entry."""
        self._send_current()

    def _on_send_clicked(self, _button: Gtk.Button) -> None:
        """Handle the **Send** button click."""
        self._send_current()

    def _on_key_press(
        self,
        _widget: Gtk.Widget,
        event: Gdk.EventKey,
    ) -> bool:
        """Handle Up / Down arrow for history navigation.

        Returns
        -------
        bool
            ``True`` if the event was consumed.
        """
        keyval = event.keyval

        if keyval == Gdk.KEY_Up:
            self._history_navigate(-1)
            return True
        if keyval == Gdk.KEY_Down:
            self._history_navigate(1)
            return True

        return False

    # ── Internal helpers ─────────────────────────────────────────

    def _send_current(self) -> None:
        """Emit *send-command* with the entry text and push to history."""
        text = self._entry.get_text().strip()
        if not text:
            return
        self._push_history(text)
        self.emit("send-command", text)
        self._entry.set_text("")
        self._history_index = -1
        logger.debug("Broadcast command: %s", text)

    def _push_history(self, text: str) -> None:
        """Append *text* to the history ring, deduplicating the tail."""
        if self._history and self._history[-1] == text:
            return
        self._history.append(text)
        if len(self._history) > _MAX_HISTORY:
            self._history = self._history[-_MAX_HISTORY:]

    def _history_navigate(self, direction: int) -> None:
        """Move through the history ring.

        Parameters
        ----------
        direction:
            ``-1`` to go back (Up), ``1`` to go forward (Down).
        """
        if not self._history:
            return

        if self._history_index == -1:
            self._saved_entry = self._entry.get_text()

        new_index = self._history_index - direction
        if new_index < 0:
            # Back to the live entry
            self._history_index = -1
            self._entry.set_text(self._saved_entry)
            self._entry.set_position(-1)
            return
        if new_index >= len(self._history):
            return

        self._history_index = new_index
        self._entry.set_text(self._history[-(new_index + 1)])
        self._entry.set_position(-1)

    def _update_sensitivity(self) -> None:
        """Grey-out children when broadcasting is disabled."""
        active = self._toggle.get_active()
        self._entry.set_sensitive(active)
        self._include_current.set_sensitive(active)
