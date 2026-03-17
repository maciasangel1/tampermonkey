"""Macro recording and playback for FedoraXTerm.

Records sequences of commands and replays them into a terminal.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from fedoraxterm.settings import _data_dir


@dataclass
class Macro:
    """A recorded macro — a named sequence of commands."""

    name: str
    commands: list[str] = field(default_factory=list)
    delay_ms: int = 200  # milliseconds between commands


class MacroManager:
    """Manages loading, saving, and executing macros."""

    def __init__(self, data_dir: Optional[Path] = None):
        self._dir = data_dir or (_data_dir() / "macros")
        self._dir.mkdir(parents=True, exist_ok=True)
        self.macros: list[Macro] = []
        self._recording = False
        self._current_macro: Optional[Macro] = None
        self.load()

    # -- persistence --------------------------------------------------------

    def load(self):
        """Load all macros from disk."""
        self.macros.clear()
        macro_file = self._dir / "macros.json"
        if macro_file.exists():
            try:
                with open(macro_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self.macros = [Macro(**m) for m in data]
            except (json.JSONDecodeError, TypeError):
                self.macros = []

    def save(self):
        """Persist macros to disk."""
        macro_file = self._dir / "macros.json"
        with open(macro_file, "w", encoding="utf-8") as fh:
            json.dump([asdict(m) for m in self.macros], fh, indent=2)

    # -- recording ----------------------------------------------------------

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start_recording(self, name: str):
        """Begin recording a new macro."""
        self._current_macro = Macro(name=name)
        self._recording = True

    def record_command(self, command: str):
        """Add a command to the current macro being recorded."""
        if self._recording and self._current_macro is not None:
            self._current_macro.commands.append(command)

    def stop_recording(self) -> Optional[Macro]:
        """Stop recording and save the macro."""
        self._recording = False
        macro = self._current_macro
        self._current_macro = None
        if macro and macro.commands:
            self.macros.append(macro)
            self.save()
        return macro

    # -- playback -----------------------------------------------------------

    def play(self, name: str, terminal) -> bool:
        """Play a macro into *terminal* using GLib timeouts.

        Args:
            name: Macro name.
            terminal: A ``TerminalWidget`` instance.

        Returns:
            ``True`` if the macro was found, ``False`` otherwise.
        """
        from gi.repository import GLib

        macro = next((m for m in self.macros if m.name == name), None)
        if macro is None:
            return False

        for idx, cmd in enumerate(macro.commands):
            GLib.timeout_add(macro.delay_ms * idx, terminal.feed_command, cmd)
        return True

    def delete(self, name: str):
        """Delete a macro by name."""
        self.macros = [m for m in self.macros if m.name != name]
        self.save()


# ---------------------------------------------------------------------------
# GTK Dialog — created via factory to avoid top-level GTK imports
# ---------------------------------------------------------------------------


def create_macro_dialog(parent, macro_manager, play_callback=None):
    """Create and return a MacroDialog instance.

    GTK is imported lazily so that the pure-logic classes above remain
    usable without a display server.
    """
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib

    class MacroDialog(Gtk.Dialog):
        """Dialog for managing and playing macros."""

        def __init__(self, parent_win, mm, play_cb=None):
            super().__init__(
                title="Macro Manager",
                transient_for=parent_win,
                modal=False,
                default_width=500,
                default_height=400,
            )
            self.add_button("_Close", Gtk.ResponseType.CLOSE)
            self.connect("response", lambda d, _r: d.destroy())

            self._mm = mm
            self._play_cb = play_cb

            content = self.get_content_area()
            content.set_spacing(6)
            content.set_margin_start(8)
            content.set_margin_end(8)
            content.set_margin_top(8)
            content.set_margin_bottom(8)

            toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            for label, cb in [
                ("Play", self._on_play),
                ("Delete", self._on_delete),
            ]:
                btn = Gtk.Button(label=label)
                btn.connect("clicked", cb)
                toolbar.pack_start(btn, False, False, 0)
            content.pack_start(toolbar, False, False, 0)

            self._store = Gtk.ListStore(str, int)
            self._tree = Gtk.TreeView(model=self._store)
            for idx, title in enumerate(["Name", "Commands"]):
                col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=idx)
                col.set_expand(idx == 0)
                self._tree.append_column(col)

            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scroll.add(self._tree)
            content.pack_start(scroll, True, True, 0)

            self._refresh()
            self.show_all()

        def _refresh(self):
            self._store.clear()
            for m in self._mm.macros:
                self._store.append([m.name, len(m.commands)])

        def _get_selected(self):
            sel = self._tree.get_selection()
            model, it = sel.get_selected()
            if it:
                return model.get_value(it, 0)
            return None

        def _on_play(self, _btn):
            name = self._get_selected()
            if name and self._play_cb:
                self._play_cb(name)

        def _on_delete(self, _btn):
            name = self._get_selected()
            if name:
                self._mm.delete(name)
                self._refresh()

    return MacroDialog(parent_win=parent, mm=macro_manager, play_cb=play_callback)
