#!/usr/bin/env bash
# install.sh – Install FedoraXTerm on Fedora Linux
set -euo pipefail

# ── Check for Fedora ────────────────────────────────────────────────
if [[ ! -f /etc/fedora-release ]]; then
    echo "ERROR: This installer is intended for Fedora Linux." >&2
    exit 1
fi

FEDORA_VERSION=$(rpm -E %fedora)
echo "==> Detected Fedora ${FEDORA_VERSION}"

# ── Install system dependencies ─────────────────────────────────────
echo "==> Installing system dependencies …"
sudo dnf install -y \
    python3-gobject \
    python3-pip \
    python3-devel \
    gtk3 \
    vte291 \
    vte291-devel \
    openssh-clients \
    openssl-devel \
    gobject-introspection-devel \
    cairo-gobject-devel \
    pkg-config

# ── Install FedoraXTerm via pip (user mode) ─────────────────────────
echo "==> Installing FedoraXTerm …"
pip install --user .

# ── Install desktop file ────────────────────────────────────────────
DESKTOP_SRC="fedoraxterm/resources/fedoraxterm.desktop"
DESKTOP_DST="${HOME}/.local/share/applications/fedoraxterm.desktop"

if [[ -f "${DESKTOP_SRC}" ]]; then
    echo "==> Installing desktop entry → ${DESKTOP_DST}"
    install -Dm644 "${DESKTOP_SRC}" "${DESKTOP_DST}"
fi

# ── Install icon ────────────────────────────────────────────────────
ICON_SRC="fedoraxterm/resources/fedoraxterm.svg"
ICON_DST="${HOME}/.local/share/icons/hicolor/scalable/apps/fedoraxterm.svg"

if [[ -f "${ICON_SRC}" ]]; then
    echo "==> Installing icon → ${ICON_DST}"
    install -Dm644 "${ICON_SRC}" "${ICON_DST}"
fi

echo "==> FedoraXTerm installed successfully."
echo "    Run with: fedoraxterm"
