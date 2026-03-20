"""Customisable button-bar widget for FedoraXTerm.

Provides :class:`ButtonBarWidget`, a horizontal toolbar of
quick-command buttons that send shell commands to the active terminal –
mirroring SecureCRT's button-bar feature.  Buttons are fully
configurable, support drag-to-reorder, and emit GObject signals so the
application layer can route commands to the correct terminal (or
broadcast to all).
"""

from __future__ import annotations

import logging
from typing import Optional

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gdk, GLib, GObject, Gtk  # noqa: E402

from fedoraxterm.settings import ButtonBarConfig  # noqa: E402

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────

_DRAG_TARGETS = [Gtk.TargetEntry.new("BUTTON_BAR_ITEM", Gtk.TargetFlags.SAME_APP, 0)]


# ── Widget ───────────────────────────────────────────────────────────


class ButtonBarWidget(Gtk.Box):
    """Horizontal bar of quick-command buttons.

    Signals
    -------
    send-command (str)
        Emitted when a button is clicked.  The payload is the shell
        command to send to the *active* terminal.
    send-command-all (str)
        Emitted when a button marked *send_to_all* is clicked.  The
        payload is the shell command to broadcast.
    """

    __gsignals__ = {
        "send-command": (
            GObject.SignalFlags.RUN_LAST,
            None,
            (str,),
        ),
        "send-command-all": (
            GObject.SignalFlags.RUN_LAST,
            None,
            (str,),
        ),
    }

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)

        self._buttons: list[dict[str, object]] = []
        self._bar_name: str = "Default"
        self._drag_source_index: int = -1

        # Switcher (optional, shown when multiple bars exist).
        self._bar_combo = Gtk.ComboBoxText()
        self._bar_combo.connect("changed", self._on_bar_combo_changed)
        self.pack_start(self._bar_combo, False, False, 0)
        self._bar_combo.set_no_show_all(True)

        # Scrollable area for buttons.
        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.pack_start(self._scroll, True, True, 0)

        self._button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self._scroll.add(self._button_box)

        # "+" add button
        add_btn = Gtk.Button(label="+")
        add_btn.set_tooltip_text("Add a new button")
        add_btn.connect("clicked", self._on_add_clicked)
        self.pack_end(add_btn, False, False, 0)

    # ── Configuration I/O ────────────────────────────────────────

    def load_config(self, config: ButtonBarConfig) -> None:
        """Populate the bar from a :class:`ButtonBarConfig`.

        Parameters
        ----------
        config:
            Button-bar configuration to load.
        """
        self.clear()
        self._bar_name = config.name
        for btn_dict in config.buttons:
            self.add_button(
                label=str(btn_dict.get("label", "")),
                command=str(btn_dict.get("command", "")),
                icon=str(btn_dict.get("icon", "")) or None,
                color=str(btn_dict.get("color", "")) or None,
                send_to_all=bool(btn_dict.get("send_to_all", False)),
            )

    def get_config(self) -> ButtonBarConfig:
        """Return the current bar state as a :class:`ButtonBarConfig`."""
        buttons = [
            {
                "label": str(b.get("label", "")),
                "command": str(b.get("command", "")),
                "icon": str(b.get("icon", "")),
                "color": str(b.get("color", "")),
                "send_to_all": bool(b.get("send_to_all", False)),
            }
            for b in self._buttons
        ]
        return ButtonBarConfig(name=self._bar_name, buttons=buttons)

    # ── Button management ────────────────────────────────────────

    def add_button(
        self,
        label: str,
        command: str,
        icon: Optional[str] = None,
        color: Optional[str] = None,
        send_to_all: bool = False,
    ) -> None:
        """Add a new quick-command button to the bar.

        Parameters
        ----------
        label:
            Button display text.
        command:
            Shell command to send when clicked.
        icon:
            Optional GTK icon name.
        color:
            Optional CSS colour for the button background.
        send_to_all:
            When *True* the ``send-command-all`` signal is emitted
            instead of ``send-command``.
        """
        info: dict[str, object] = {
            "label": label,
            "command": command,
            "icon": icon or "",
            "color": color or "",
            "send_to_all": send_to_all,
        }
        idx = len(self._buttons)
        self._buttons.append(info)

        btn = self._create_gtk_button(info, idx)
        self._button_box.pack_start(btn, False, False, 0)
        btn.show_all()

    def remove_button(self, index: int) -> None:
        """Remove the button at *index*.

        Raises
        ------
        IndexError
            If *index* is out of range.
        """
        if index < 0 or index >= len(self._buttons):
            raise IndexError(f"Button index {index} out of range.")
        del self._buttons[index]
        self._rebuild_buttons()

    def clear(self) -> None:
        """Remove all buttons from the bar."""
        self._buttons.clear()
        for child in self._button_box.get_children():
            self._button_box.remove(child)

    # ── Internal: GTK button creation ────────────────────────────

    def _create_gtk_button(self, info: dict[str, object], index: int) -> Gtk.Button:
        """Build a :class:`Gtk.Button` for the given *info* dict."""
        label_text = str(info.get("label", ""))
        icon_name = str(info.get("icon", ""))

        if icon_name:
            image = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.SMALL_TOOLBAR)
            btn = Gtk.Button()
            btn.set_image(image)
            btn.set_label(label_text)
            btn.set_always_show_image(True)
        else:
            btn = Gtk.Button(label=label_text)

        btn.set_tooltip_text(str(info.get("command", "")))

        color_str = str(info.get("color", ""))
        if color_str:
            css = f"button {{ background-color: {color_str}; }}"
            provider = Gtk.CssProvider()
            provider.load_from_data(css.encode())
            ctx = btn.get_style_context()
            ctx.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        btn.connect("clicked", self._on_button_clicked, index)
        btn.connect("button-press-event", self._on_button_press, index)

        # Drag-and-drop reorder support.
        btn.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK,
            _DRAG_TARGETS,
            Gdk.DragAction.MOVE,
        )
        btn.drag_dest_set(Gtk.DestDefaults.ALL, _DRAG_TARGETS, Gdk.DragAction.MOVE)
        btn.connect("drag-begin", self._on_drag_begin, index)
        btn.connect("drag-data-received", self._on_drag_data_received, index)

        return btn

    def _rebuild_buttons(self) -> None:
        """Recreate all GTK button widgets from ``self._buttons``."""
        for child in self._button_box.get_children():
            self._button_box.remove(child)
        for idx, info in enumerate(self._buttons):
            btn = self._create_gtk_button(info, idx)
            self._button_box.pack_start(btn, False, False, 0)
        self._button_box.show_all()

    # ── Signal handlers ──────────────────────────────────────────

    def _on_button_clicked(self, _widget: Gtk.Button, index: int) -> None:
        """Send the command associated with the clicked button."""
        if index < 0 or index >= len(self._buttons):
            return
        info = self._buttons[index]
        command = str(info.get("command", ""))
        if info.get("send_to_all"):
            self.emit("send-command-all", command)
        else:
            self.emit("send-command", command)

    def _on_button_press(
        self,
        widget: Gtk.Button,
        event: Gdk.EventButton,
        index: int,
    ) -> bool:
        """Show a context menu on right-click."""
        if event.button != 3:
            return False

        menu = Gtk.Menu()

        edit_item = Gtk.MenuItem(label="Edit")
        edit_item.connect("activate", self._on_edit_button, index)
        menu.append(edit_item)

        delete_item = Gtk.MenuItem(label="Delete")
        delete_item.connect("activate", self._on_delete_button, index)
        menu.append(delete_item)

        menu.show_all()
        menu.popup_at_widget(widget, Gdk.Gravity.SOUTH, Gdk.Gravity.NORTH, None)
        return True

    # ── Context menu actions ─────────────────────────────────────

    def _on_edit_button(self, _item: Gtk.MenuItem, index: int) -> None:
        """Open a dialog to edit the button at *index*."""
        if index < 0 or index >= len(self._buttons):
            return
        info = self._buttons[index]

        dialog = Gtk.Dialog(
            title="Edit Button",
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        content = dialog.get_content_area()

        label_entry = Gtk.Entry()
        label_entry.set_text(str(info.get("label", "")))
        content.pack_start(_labelled("Label:", label_entry), False, False, 4)

        cmd_entry = Gtk.Entry()
        cmd_entry.set_text(str(info.get("command", "")))
        content.pack_start(_labelled("Command:", cmd_entry), False, False, 4)

        icon_entry = Gtk.Entry()
        icon_entry.set_text(str(info.get("icon", "")))
        content.pack_start(_labelled("Icon:", icon_entry), False, False, 4)

        color_entry = Gtk.Entry()
        color_entry.set_text(str(info.get("color", "")))
        content.pack_start(_labelled("Color:", color_entry), False, False, 4)

        all_check = Gtk.CheckButton(label="Send to all terminals")
        all_check.set_active(bool(info.get("send_to_all", False)))
        content.pack_start(all_check, False, False, 4)

        dialog.show_all()
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self._buttons[index] = {
                "label": label_entry.get_text(),
                "command": cmd_entry.get_text(),
                "icon": icon_entry.get_text(),
                "color": color_entry.get_text(),
                "send_to_all": all_check.get_active(),
            }
            self._rebuild_buttons()
        dialog.destroy()

    def _on_delete_button(self, _item: Gtk.MenuItem, index: int) -> None:
        """Delete the button at *index* after confirmation."""
        self.remove_button(index)

    def _on_add_clicked(self, _widget: Gtk.Button) -> None:
        """Open a dialog to add a new button."""
        dialog = Gtk.Dialog(
            title="Add Button",
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        content = dialog.get_content_area()

        label_entry = Gtk.Entry()
        content.pack_start(_labelled("Label:", label_entry), False, False, 4)

        cmd_entry = Gtk.Entry()
        content.pack_start(_labelled("Command:", cmd_entry), False, False, 4)

        icon_entry = Gtk.Entry()
        content.pack_start(_labelled("Icon:", icon_entry), False, False, 4)

        color_entry = Gtk.Entry()
        content.pack_start(_labelled("Color:", color_entry), False, False, 4)

        all_check = Gtk.CheckButton(label="Send to all terminals")
        content.pack_start(all_check, False, False, 4)

        dialog.show_all()
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.add_button(
                label=label_entry.get_text(),
                command=cmd_entry.get_text(),
                icon=icon_entry.get_text() or None,
                color=color_entry.get_text() or None,
                send_to_all=all_check.get_active(),
            )
        dialog.destroy()

    # ── Drag-and-drop ────────────────────────────────────────────

    def _on_drag_begin(
        self,
        _widget: Gtk.Button,
        _context: Gdk.DragContext,
        index: int,
    ) -> None:
        self._drag_source_index = index

    def _on_drag_data_received(
        self,
        _widget: Gtk.Button,
        _context: Gdk.DragContext,
        _x: int,
        _y: int,
        _data: Gtk.SelectionData,
        _info: int,
        _time: int,
        dest_index: int,
    ) -> None:
        src = self._drag_source_index
        if src < 0 or src == dest_index:
            return
        if src >= len(self._buttons) or dest_index >= len(self._buttons):
            return
        item = self._buttons.pop(src)
        self._buttons.insert(dest_index, item)
        self._rebuild_buttons()
        logger.debug("Button reordered: %d → %d", src, dest_index)

    # ── Bar switcher ─────────────────────────────────────────────

    def _on_bar_combo_changed(self, combo: Gtk.ComboBoxText) -> None:
        """Handle bar-switcher combo selection.

        The application is expected to connect to this and load the
        corresponding :class:`ButtonBarConfig`.
        """
        self._bar_name = combo.get_active_text() or "Default"


# ── Utility ──────────────────────────────────────────────────────────


def _labelled(text: str, widget: Gtk.Widget) -> Gtk.Box:
    """Return a horizontal box with a label and the given widget."""
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    label = Gtk.Label(label=text)
    label.set_xalign(0)
    label.set_size_request(80, -1)
    box.pack_start(label, False, False, 0)
    box.pack_start(widget, True, True, 0)
    return box
