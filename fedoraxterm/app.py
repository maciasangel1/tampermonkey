"""Main GTK application class for FedoraXTerm."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio, GLib

from fedoraxterm import __app_id__, __app_name__, __version__


class FedoraXTermApp(Gtk.Application):
    """Main application class managing the FedoraXTerm lifecycle."""

    def __init__(self):
        super().__init__(
            application_id=__app_id__,
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        self.window = None
        GLib.set_application_name(__app_name__)

    def do_activate(self):
        """Handle application activation."""
        if self.window is None:
            from fedoraxterm.window import MainWindow

            self.window = MainWindow(application=self)
        self.window.present()

    def do_startup(self):
        """Handle application startup — set up actions and menus."""
        Gtk.Application.do_startup(self)
        self._setup_actions()

    def _setup_actions(self):
        """Register application-level actions."""
        actions = [
            ("quit", self._on_quit),
            ("about", self._on_about),
            ("new-local-terminal", self._on_new_local_terminal),
            ("new-ssh-session", self._on_new_ssh_session),
            ("network-tools", self._on_network_tools),
        ]
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

        self.set_accels_for_action("app.quit", ["<Primary>q"])
        self.set_accels_for_action("app.new-local-terminal", ["<Primary>t"])
        self.set_accels_for_action("app.new-ssh-session", ["<Primary>n"])

    def _on_quit(self, _action, _param):
        """Quit the application."""
        self.quit()

    def _on_about(self, _action, _param):
        """Show the about dialog."""
        dialog = Gtk.AboutDialog(
            transient_for=self.window,
            modal=True,
            program_name=__app_name__,
            version=__version__,
            comments="A MobaXterm-like terminal and SSH client for Fedora Linux",
            license_type=Gtk.License.GPL_3_0,
            website="https://github.com/maciasangel1/tampermonkey",
            authors=["FedoraXTerm Contributors"],
        )
        dialog.present()

    def _on_new_local_terminal(self, _action, _param):
        """Open a new local terminal tab."""
        if self.window:
            self.window.add_local_terminal_tab()

    def _on_new_ssh_session(self, _action, _param):
        """Open the SSH session dialog."""
        if self.window:
            self.window.show_ssh_dialog()

    def _on_network_tools(self, _action, _param):
        """Open the network tools dialog."""
        if self.window:
            self.window.show_network_tools()
