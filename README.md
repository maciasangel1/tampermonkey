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

### Option 1: Install from source (pip)

```bash
git clone https://github.com/maciasangel1/tampermonkey.git
cd tampermonkey
pip install .
```

Then run:

```bash
fedoraxterm
```

### Option 2: Run without installing

```bash
git clone https://github.com/maciasangel1/tampermonkey.git
cd tampermonkey
python -m fedoraxterm
```

### Option 3: Build and install RPM (Fedora)

```bash
# Install build tools
sudo dnf install rpm-build python3-setuptools

# Build the RPM
rpmbuild -ba fedoraxterm.spec

# Install
sudo dnf install ~/rpmbuild/RPMS/noarch/fedoraxterm-1.0.0-1.*.noarch.rpm
```

### Desktop Integration

To install the `.desktop` entry and icon system-wide:

```bash
sudo cp fedoraxterm/resources/fedoraxterm.desktop /usr/share/applications/
sudo cp fedoraxterm/resources/fedoraxterm.svg /usr/share/icons/hicolor/scalable/apps/
sudo gtk-update-icon-cache /usr/share/icons/hicolor/
```

---

## Usage

### Launching

```bash
# Installed
fedoraxterm

# From source
python -m fedoraxterm
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
pytest tests/
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

## Contributing

Contributions are welcome! Please open an issue or pull request.
