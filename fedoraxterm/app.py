"""FedoraXTerm GTK Application."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")

from gi.repository import Gio, GLib, Gtk, Vte  # noqa: E402

from fedoraxterm import __app_id__, __version__  # noqa: E402


class MainWindow(Gtk.ApplicationWindow):
    """Primary application window with an embedded VTE terminal."""

    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="FedoraXTerm")
        self.set_default_size(900, 550)

        terminal = Vte.Terminal()
        terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            None,  # working directory (inherit)
            ["/bin/bash"],
            None,  # environment (inherit)
            GLib.SpawnFlags.DEFAULT,
            None,  # child-setup callback
            None,  # child-setup data
            -1,    # timeout
            None,  # cancellable
            None,  # callback
        )

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(terminal)
        self.add(scrolled)

        terminal.connect("child-exited", lambda *_args: self.close())

        self.show_all()


class FedoraXTermApp(Gtk.Application):
    """GtkApplication for FedoraXTerm.

    Uses NON_UNIQUE so every invocation opens its own window rather than
    forwarding to an existing instance over D-Bus (which can hang when the
    bus is unavailable).
    """

    def __init__(self) -> None:
        super().__init__(
            application_id=__app_id__,
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )

    # ── Activation ───────────────────────────────────────────────────

    def do_activate(self) -> None:  # noqa: D401 – GTK override
        """Called when the application is activated."""
        MainWindow(self)

    def do_startup(self) -> None:  # noqa: D401 – GTK override
        """Called once on first activation; sets up app-level actions."""
        Gtk.Application.do_startup(self)
        self._setup_actions()

    # ── Actions ──────────────────────────────────────────────────────

    def _setup_actions(self) -> None:
        actions = {
            "quit": lambda *_a: self.quit(),
            "about": lambda *_a: self._show_about(),
            "preferences": lambda *_a: self._show_preferences(),
        }
        for name, callback in actions.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

    # ── Dialogs ──────────────────────────────────────────────────────

    def _show_about(self) -> None:
        about = Gtk.AboutDialog(
            transient_for=self.get_active_window(),
            modal=True,
            program_name="FedoraXTerm",
            version=__version__,
            comments="SecureCRT-compatible terminal emulator for Fedora Linux",
            license_type=Gtk.License.GPL_3_0,
            website="https://github.com/fedoraxterm/fedoraxterm",
            website_label="GitHub Repository",
            authors=["FedoraXTerm Contributors"],
        )
        about.run()
        about.destroy()

    @staticmethod
    def _show_preferences() -> None:
        dialog = Gtk.MessageDialog(
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Preferences",
            secondary_text="Preferences dialog is not yet implemented.",
        )
        dialog.run()
        dialog.destroy()
