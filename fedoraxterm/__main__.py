"""Entry point for FedoraXTerm application."""

import sys
import faulthandler


def main():
    """Launch the FedoraXTerm application."""
    # Enable the Python fault handler so segfaults produce a traceback on
    # stderr instead of a bare "Segmentation fault (core dumped)" message.
    faulthandler.enable()

    # NOTE: Do NOT set signal.signal(signal.SIGCHLD, signal.SIG_IGN) here.
    # VTE and GLib manage child processes via their own child-watch sources
    # which rely on receiving SIGCHLD.  Ignoring the signal breaks the
    # spawn callback and can cause hangs or zombie processes.

    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("Vte", "2.91")
        from gi.repository import Gtk, Gdk  # noqa: F401
    except (ImportError, ValueError) as e:
        print(
            f"Error: Missing required system libraries: {e}\n"
            "Please install the required dependencies:\n"
            "  sudo dnf install gtk3 vte291 python3-gobject\n",
            file=sys.stderr,
        )
        sys.exit(1)

    # Verify a display is available *before* entering the GTK main loop.
    # Without a display the application would block indefinitely.
    display = Gdk.Display.get_default()
    if display is None:
        print(
            "Error: No display found.  FedoraXTerm requires a graphical "
            "session.\nIf you are using SSH, enable X11 forwarding with "
            "'ssh -X'.",
            file=sys.stderr,
        )
        sys.exit(1)

    from fedoraxterm.app import FedoraXTermApp

    app = FedoraXTermApp()
    sys.exit(app.run(sys.argv))


if __name__ == "__main__":
    main()
