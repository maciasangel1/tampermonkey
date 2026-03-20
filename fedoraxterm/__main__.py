"""FedoraXTerm entry point.

Launch the GTK application, handling missing display servers and
import errors gracefully.
"""

from __future__ import annotations

import os
import sys


def _check_display() -> None:
    """Abort early when no display server is available."""
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        print(
            "ERROR: No display server detected. "
            "Set DISPLAY or WAYLAND_DISPLAY before launching FedoraXTerm.",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> int:
    """Application entry point."""
    _check_display()

    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("Vte", "2.91")
    except (ImportError, ValueError) as exc:
        print(
            f"ERROR: Required GObject Introspection bindings are missing:\n  {exc}\n"
            "Install them with:  sudo dnf install python3-gobject gtk3 vte291",
            file=sys.stderr,
        )
        sys.exit(1)

    # NOTE: Do NOT set signal.SIGCHLD to SIG_IGN – it breaks VTE child
    # process reaping and causes zombie / premature-exit issues.

    from fedoraxterm.app import FedoraXTermApp  # noqa: E402

    app = FedoraXTermApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
