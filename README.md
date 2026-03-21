# FedoRT

**SecureCRT-compatible terminal emulator and SSH client for Fedora Linux 43**

FedoRT is a full-featured terminal emulator and SSH client built natively
for Fedora Linux using GTK 3 and VTE. It aims to provide a familiar experience
for users migrating from SecureCRT to a Linux-native, open-source solution.

---

## Features

### Terminal Emulation
- **VTE-based terminal** with full xterm-256color support
- **Tabbed interface** – open multiple sessions in a single window
- **Split panes** – horizontal and vertical terminal splits
- **Scrollback buffer** – configurable history size
- **Search-in-terminal** – find text in scrollback

### SSH / Network Connectivity
- **SSH2 client** powered by Paramiko
- **SFTP file transfers** with progress indication
- **Key-based authentication** – RSA, Ed25519, ECDSA
- **SSH agent forwarding**
- **Port forwarding** – local, remote, and dynamic (SOCKS)
- **Jump host / ProxyCommand** support

### Session Management
- **Session profiles** – save host, port, username, key, colors, font per session
- **Session folders** – organize sessions into groups
- **Quick Connect** dialog for ad-hoc connections
- **Auto-login scripts** – send commands after connection

### Customization
- **Color schemes** – built-in themes plus custom palettes
- **Font selection** – any monospace font available on the system
- **Keyboard shortcuts** – fully remappable
- **Configurable bell** – audible, visual, or none

### Security
- **Encrypted credential storage** using the system keyring
- **Host-key verification** with known-hosts management
- **First-connect trust-on-first-use (TOFU)** with fingerprint display

### Integration
- **Desktop entry** – appears in GNOME/KDE application menus
- **D-Bus interface** – scriptable session control
- **Command-line launcher** – `fedort ssh://user@host`

---

## Requirements

| Component       | Minimum Version |
|-----------------|-----------------|
| Fedora Linux    | 43 (38+ minimum)|
| Python          | 3.11+           |
| GTK 3           | 3.24+           |
| VTE (vte291)    | 0.70+           |
| PyGObject       | 3.42+           |
| Paramiko        | 3.0+            |
| cryptography    | 42.0.4+         |

---

## Installation

### Quick Install (Fedora)

```bash
git clone https://github.com/fedort/fedort.git
cd fedort
chmod +x install.sh
./install.sh
```

### Manual Install

```bash
# Install system dependencies
sudo dnf install python3-gobject python3-pip gtk3 vte291 openssh-clients

# Install FedoRT
pip install --user --force-reinstall .

# Run
fedort
```

### RPM Build

```bash
rpmbuild -ba fedort.spec
```

---

## Usage

```bash
# Launch the GUI
fedort

# Connect directly via SSH URI
fedort ssh://user@hostname:22

# Alternative entry point
fedort-gui
```

---

## Development

```bash
# Install in editable mode
pip install -e '.[dev]'

# Run tests
pytest

# Run a specific test
pytest tests/test_app.py -v
```

---

## Project Structure

```
fedort/
├── __init__.py          # Package metadata
├── __main__.py          # Entry point
├── app.py               # GtkApplication
└── resources/
    ├── fedort.desktop
    └── fedort.svg
tests/
    └── __init__.py
pyproject.toml           # Project configuration
setup.py                 # Backward-compat shim
install.sh               # Fedora installer
fedort.spec         # RPM spec file
COPYING                  # GPL-3.0 license
README.md                # This file
```

---

## License

FedoRT is licensed under the
[GNU General Public License v3.0 or later](COPYING).

---

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -am 'Add my feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request
