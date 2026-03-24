"""Multi-execution panel for FedoraXTerm.

Allows broadcasting a command to multiple terminal tabs simultaneously,
mimicking MobaXterm's "MultiExec" feature.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class MultiExecBar(Gtk.Box):
    """A toolbar that sends a command to all (or selected) terminals."""

    def __init__(self, get_terminals_callback=None):
        """
        Args:
            get_terminals_callback: A callable returning a list of
                ``(tab_label, TerminalWidget)`` tuples.
        """
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.set_margin_start(6)
        self.set_margin_end(6)
        self.set_margin_top(4)
        self.set_margin_bottom(4)

        self._get_terminals = get_terminals_callback

        icon = Gtk.Image.new_from_icon_name(
            "system-run-symbolic", Gtk.IconSize.SMALL_TOOLBAR
        )
        self.pack_start(icon, False, False, 0)

        label = Gtk.Label(label="MultiExec:")
        self.pack_start(label, False, False, 0)

        self._entry = Gtk.Entry()
        self._entry.set_hexpand(True)
        self._entry.set_placeholder_text(
            "Type a command and press Enter to send to all terminals…"
        )
        self._entry.connect("activate", self._on_send)
        self.pack_start(self._entry, True, True, 0)

        send_btn = Gtk.Button(label="Send")
        send_btn.connect("clicked", self._on_send)
        self.pack_start(send_btn, False, False, 0)

        self._enabled = Gtk.CheckButton(label="Enabled")
        self._enabled.set_active(False)
        self.pack_start(self._enabled, False, False, 0)

    @property
    def enabled(self) -> bool:
        return self._enabled.get_active()

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled.set_active(value)

    def _on_send(self, _widget):
        """Broadcast the entry text to all terminals."""
        if not self.enabled:
            return
        cmd = self._entry.get_text()
        if not cmd:
            return

        if self._get_terminals:
            for _label, terminal in self._get_terminals():
                terminal.feed_command(cmd)
        self._entry.set_text("")
