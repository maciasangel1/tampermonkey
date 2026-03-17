#!/usr/bin/env bash
# install.sh — One-command installer for FedoraXTerm on Fedora 43+
#
# Usage:
#   chmod +x install.sh
#   ./install.sh
#
# This script will:
#   1. Install required system packages (GTK3, VTE, PyGObject, etc.)
#   2. Install the FedoraXTerm Python package via pip
#   3. Install the desktop entry and application icon
#
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# --- Ensure we're in the repository root ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f "pyproject.toml" ]; then
    error "pyproject.toml not found. Please run this script from the repository root."
    error "  cd /path/to/tampermonkey && ./install.sh"
    exit 1
fi

info "=== FedoraXTerm Installer ==="
echo

# --- Step 1: Install system dependencies ---
info "Step 1/3: Installing system dependencies..."
PACKAGES=(
    python3
    python3-pip
    python3-gobject
    gtk3
    vte291
    python3-paramiko
    openssh-clients
)

OPTIONAL_PACKAGES=(
    freerdp
    tigervnc
    telnet
    minicom
    traceroute
    bind-utils
    gtksourceview3
)

if command -v dnf &>/dev/null; then
    info "Using dnf to install required packages..."
    sudo dnf install -y "${PACKAGES[@]}" 2>&1 | tail -5
    info "Installing optional (recommended) packages..."
    sudo dnf install -y "${OPTIONAL_PACKAGES[@]}" 2>&1 | tail -5 || warn "Some optional packages could not be installed (this is OK)."
else
    error "dnf not found. This installer is designed for Fedora."
    error "Please install the following packages manually:"
    echo "  ${PACKAGES[*]}"
    exit 1
fi
echo

# --- Step 2: Install FedoraXTerm Python package ---
info "Step 2/3: Installing FedoraXTerm Python package..."
pip install --user . 2>&1 | tail -5

# Verify the command is available
if command -v fedoraxterm &>/dev/null; then
    info "fedoraxterm command is available."
elif [ -f "$HOME/.local/bin/fedoraxterm" ]; then
    warn "fedoraxterm installed to ~/.local/bin/fedoraxterm"
    warn "Make sure ~/.local/bin is in your PATH:"
    echo '  export PATH="$HOME/.local/bin:$PATH"'
    echo '  # Add the line above to your ~/.bashrc to make it permanent.'
else
    warn "Could not locate fedoraxterm binary. You can still run:"
    echo "  python3 -m fedoraxterm"
fi
echo

# --- Step 3: Desktop integration ---
info "Step 3/3: Installing desktop entry and icon..."
DESKTOP_FILE="fedoraxterm/resources/fedoraxterm.desktop"
ICON_FILE="fedoraxterm/resources/fedoraxterm.svg"

if [ -f "$DESKTOP_FILE" ] && [ -f "$ICON_FILE" ]; then
    sudo install -Dm644 "$DESKTOP_FILE" /usr/share/applications/fedoraxterm.desktop
    sudo install -Dm644 "$ICON_FILE" /usr/share/icons/hicolor/scalable/apps/fedoraxterm.svg
    sudo gtk-update-icon-cache /usr/share/icons/hicolor/ 2>/dev/null || true
    info "Desktop entry and icon installed."
else
    warn "Desktop files not found, skipping desktop integration."
fi
echo

info "=== Installation complete! ==="
echo
echo "To launch FedoraXTerm:"
echo "  fedoraxterm"
echo
echo "Or run directly with Python:"
echo "  python3 -m fedoraxterm"
echo
