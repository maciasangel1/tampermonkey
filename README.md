# FedoraXTerm

**A MobaXterm-like terminal and remote-computing toolbox for Fedora Linux**

FedoraXTerm brings the power of [MobaXterm](https://mobaxterm.mobatek.net/) to Fedora 43 and other modern Linux distributions. It provides a unified, tabbed interface for terminal emulation, remote connections, file transfers, and network diagnostics — all in a single application.

---

## Features

| Feature | Description |
|---|---|
| **Tabbed Terminal Emulator** | Multiple local shell terminals with VTE, custom colors & fonts |
| **SSH Client** | Connect to remote servers with password or key authentication |
| **SFTP File Browser** | Graphical remote file browser (auto-opens with SSH sessions) |
| **RDP Client** | Remote Desktop connections via `xfreerdp` |
| **VNC Client** | VNC remote desktop sessions via `vncviewer` |
| **Telnet** | Classic Telnet connections |
| **Serial Console** | Connect to serial/COM ports via `minicom` or `screen` |
| **Session Manager** | Save, organise (with folders), and quick-connect to sessions |
| **SSH Tunnel Manager** | Create and manage local/remote SSH port-forwarding tunnels |
| **Network Tools** | Ping, Traceroute, NSLookup, TCP port scanner |
| **Multi-Execution** | Broadcast a command to all open terminal tabs simultaneously |
| **Macro Recording** | Record command sequences and replay them |
| **Built-in Text Editor** | Edit local and remote files (with optional GtkSourceView syntax highlighting) |
| **Keyboard Shortcuts** | `Ctrl+T` new terminal, `Ctrl+N` new SSH session, `Ctrl+Q` quit |

---

## Screenshots

*FedoraXTerm provides a three-panel layout inspired by MobaXterm:*

```
┌──────────┬────────────────────────────────┬────────────┐
│ Sessions │  Tabbed Terminal Area          │ SFTP       │
│ Sidebar  │  ┌──────┬──────┬──────┐       │ Browser    │
│          │  │ SSH1 │ SSH2 │Shell │       │            │
│ 📁 Default│  ├──────┴──────┴──────┤       │ /home/user │
│  └ web01 │  │ $ ssh user@server   │       │ ├─ docs/   │
│  └ db01  │  │ Connected.          │       │ ├─ src/    │
│ 📁 Prod  │  │ $ _                 │       │ └─ file.py │
│  └ app01 │  │                     │       │            │
│          │  │                     │       │            │
├──────────┴──┴─────────────────────┴───────┴────────────┤
│ MultiExec: [type command here to send to all terminals]│
├────────────────────────────────────────────────────────┤
│ Ready                                                  │
└────────────────────────────────────────────────────────┘
```

---

## Requirements

### System (Fedora 43)

```bash
# Required
sudo dnf install python3 python3-gobject gtk3 vte291 python3-pip

# Recommended (for full feature set)
sudo dnf install \
    python3-paramiko \
    openssh-clients \
    freerdp \
    tigervnc \
    telnet \
    minicom \
    traceroute \
    bind-utils \
    gtksourceview3
```

### Python

- Python ≥ 3.11
- PyGObject ≥ 3.42
- paramiko ≥ 3.0 (for SFTP browser)

---

## Installation

### Option 1: Quick Install (recommended for Fedora)

```bash
git clone https://github.com/maciasangel1/tampermonkey.git
cd tampermonkey
chmod +x install.sh
./install.sh
```

The `install.sh` script will automatically:
1. Install all required system packages via `dnf`
2. Install FedoraXTerm via `pip`
3. Set up the desktop entry and application icon

### Option 2: Manual install from source (pip)

```bash
# 1. Install system dependencies first
sudo dnf install python3 python3-pip python3-gobject gtk3 vte291

# 2. Clone and install
git clone https://github.com/maciasangel1/tampermonkey.git
cd tampermonkey
pip install --user .
```

Then run:

```bash
fedoraxterm
```

> **Note:** If `fedoraxterm` is not found after install, make sure `~/.local/bin`
> is in your `PATH`:
> ```bash
> export PATH="$HOME/.local/bin:$PATH"
> ```
> Add the line above to your `~/.bashrc` to make it permanent.

### Option 3: Run without installing

```bash
# Install system dependencies first
sudo dnf install python3 python3-pip python3-gobject gtk3 vte291 python3-paramiko

git clone https://github.com/maciasangel1/tampermonkey.git
cd tampermonkey
python3 -m fedoraxterm
```

### Option 4: Build and install RPM (Fedora)

```bash
# Install build tools
sudo dnf install rpm-build python3-setuptools

# Clone the repository
git clone https://github.com/maciasangel1/tampermonkey.git
cd tampermonkey

# Build the RPM (run from inside the repo directory)
rpmbuild -ba fedoraxterm.spec

# Install
sudo dnf install ~/rpmbuild/RPMS/noarch/fedoraxterm-1.0.0-1.*.noarch.rpm
```

### Desktop Integration

To manually install the `.desktop` entry and icon system-wide:

```bash
cd tampermonkey
sudo install -Dm644 fedoraxterm/resources/fedoraxterm.desktop /usr/share/applications/fedoraxterm.desktop
sudo install -Dm644 fedoraxterm/resources/fedoraxterm.svg /usr/share/icons/hicolor/scalable/apps/fedoraxterm.svg
sudo gtk-update-icon-cache /usr/share/icons/hicolor/
```

---

## Usage

### Launching

```bash
# If installed via pip
fedoraxterm

# Or run directly from the repository
python3 -m fedoraxterm
```

### Quick SSH Connection

1. Type `user@hostname` in the **Quick Connect** bar at the bottom of the sidebar
2. Press Enter or click **Connect**

### Session Management

1. Click **+** in the Sessions sidebar (or `Sessions → New SSH Session`)
2. Fill in host, port, username, authentication method
3. Sessions are saved automatically and appear grouped by folder

### SSH Tunnels

1. Open `Tools → SSH Tunnel Manager`
2. Click **Add** to define a local or remote port-forward
3. Click **Start** to activate the tunnel

### Multi-Execution

1. Enable via `View → MultiExec Bar`
2. Check the **Enabled** checkbox
3. Type a command and press Enter — it is sent to **all** open terminals

### Macros

1. `Macros → Start Recording` — enter a name
2. Commands you type are recorded
3. `Macros → Stop Recording`
4. Play back via `Tools → Macro Manager`

### Network Tools

`Tools → Network Tools` opens a dialog with:
- **Ping** — ICMP echo requests
- **Traceroute** — network path tracing
- **NSLookup** — DNS resolution
- **Port Scan** — TCP scan of common ports

### Text Editor

`Tools → Text Editor` opens a tabbed editor with:
- Syntax highlighting (if GtkSourceView is installed)
- Line numbers
- Open / Save / Save As

---

## Architecture

```
fedoraxterm/
├── __init__.py            # Package metadata
├── __main__.py            # Entry point
├── app.py                 # GtkApplication subclass
├── window.py              # Main window layout (MobaXterm-like)
├── terminal.py            # VTE terminal widget
├── ssh_client.py          # SSH command builder
├── sftp_browser.py        # Paramiko-based SFTP file browser
├── session_manager.py     # Sidebar + session CRUD
├── settings.py            # XDG-compliant settings & session persistence
├── network_tools.py       # Ping, traceroute, nslookup, port scan
├── tunnel_manager.py      # SSH tunnel (port-forward) manager
├── multi_exec.py          # MultiExec bar (broadcast to all terminals)
├── macro_manager.py       # Macro recording & playback
├── text_editor.py         # Built-in text editor
├── remote_sessions.py     # RDP, VNC, Telnet, serial session builders
└── resources/
    ├── fedoraxterm.desktop
    └── fedoraxterm.svg
```

### Key Technologies

| Technology | Purpose |
|---|---|
| **Python 3** | Application language |
| **GTK 3 / PyGObject** | GUI toolkit (native on GNOME / Fedora) |
| **VTE** | Terminal emulator widget |
| **Paramiko** | SFTP file browser |
| **OpenSSH** | SSH connections (system `ssh` binary) |
| **xfreerdp** | RDP remote desktop |
| **vncviewer** | VNC remote desktop |
| **minicom / screen** | Serial console |

---

## Configuration

Settings are stored in XDG-compliant locations:

| File | Location |
|---|---|
| Settings | `~/.config/fedoraxterm/settings.json` |
| Sessions | `~/.config/fedoraxterm/sessions.json` |
| Macros | `~/.local/share/fedoraxterm/macros/macros.json` |

---

## Running Tests

```bash
pip install pytest
python3 -m pytest tests/
```

---

## License

This project is licensed under the [GNU General Public License v3.0](COPYING).

---

## Comparison with MobaXterm

| Feature | MobaXterm (Windows) | FedoraXTerm (Linux) |
|---|---|---|
| Tabbed terminals | ✅ | ✅ |
| SSH client | ✅ | ✅ (system OpenSSH) |
| SFTP browser | ✅ | ✅ (Paramiko) |
| X11 server | ✅ (embedded) | N/A (native on Linux) |
| RDP client | ✅ | ✅ (xfreerdp) |
| VNC client | ✅ | ✅ (vncviewer) |
| Telnet | ✅ | ✅ |
| Serial console | ✅ | ✅ (minicom/screen) |
| Session manager | ✅ | ✅ |
| SSH tunnels | ✅ | ✅ |
| Multi-execution | ✅ | ✅ |
| Macros | ✅ | ✅ |
| Network tools | ✅ | ✅ |
| Text editor | ✅ | ✅ |
| Unix commands | ✅ (Cygwin) | N/A (native) |
| Password manager | ✅ | Planned |
| Embedded servers | ✅ | Planned |

---

## Troubleshooting

### `pip install .` fails with "Neither 'setup.py' nor 'pyproject.toml' found"

Make sure you are running the command from inside the cloned repository directory:

```bash
cd tampermonkey
pip install --user .
```

If pip is very old, upgrade it first:

```bash
pip install --upgrade pip
```

### `fedoraxterm: command not found`

The `fedoraxterm` binary is installed to `~/.local/bin/` when using `pip install --user`.
Add it to your PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Add that line to your `~/.bashrc` to make it permanent:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Alternatively, run directly without installing:

```bash
cd tampermonkey
python3 -m fedoraxterm
```

### RPM build fails with "failed to stat fedoraxterm.spec: No such file or directory"

Run `rpmbuild` from inside the repository directory:

```bash
cd tampermonkey
rpmbuild -ba fedoraxterm.spec
```

### Missing GTK/VTE libraries

If you see errors about missing Gtk or Vte namespaces, install the system libraries:

```bash
sudo dnf install python3-gobject gtk3 vte291
```

---

## Contributing

Contributions are welcome! Please open an issue or pull request.
