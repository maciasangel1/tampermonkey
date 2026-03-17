"""Entry point for FedoraXTerm application."""

import sys


def main():
    """Launch the FedoraXTerm application."""
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("Vte", "2.91")
        from gi.repository import Gtk
    except (ImportError, ValueError) as e:
        print(
            f"Error: Missing required system libraries: {e}\n"
            "Please install the required dependencies:\n"
            "  sudo dnf install gtk3 vte291 python3-gobject\n",
            file=sys.stderr,
        )
        sys.exit(1)

    from fedoraxterm.app import FedoraXTermApp

    app = FedoraXTermApp()
    sys.exit(app.run(sys.argv))


if __name__ == "__main__":
    main()
