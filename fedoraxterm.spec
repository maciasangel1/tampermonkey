Name:           fedoraxterm
Version:        1.0.0
Release:        1%{?dist}
Summary:        A MobaXterm-like terminal and SSH client for Fedora Linux

License:        GPL-3.0-or-later
URL:            https://github.com/maciasangel1/tampermonkey
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools

Requires:       python3 >= 3.11
Requires:       python3-gobject
Requires:       gtk3
Requires:       vte291
Requires:       python3-paramiko
Requires:       openssh-clients

# Optional but recommended
Recommends:     freerdp
Recommends:     tigervnc
Recommends:     telnet
Recommends:     minicom
Recommends:     traceroute
Recommends:     bind-utils
Recommends:     gtksourceview3

%description
FedoraXTerm is a comprehensive remote-computing toolbox for Fedora Linux,
inspired by MobaXterm for Windows. It provides a tabbed terminal emulator
with built-in SSH, SFTP, RDP, VNC, Telnet, and serial-console support,
along with network diagnostic tools, SSH tunnel management, macro recording,
multi-execution, and a built-in text editor.

%prep
%autosetup -n %{name}-%{version}

%build
%py3_build

%install
%py3_install

# Desktop entry
install -Dm644 fedoraxterm/resources/fedoraxterm.desktop \
    %{buildroot}%{_datadir}/applications/fedoraxterm.desktop

# Icon
install -Dm644 fedoraxterm/resources/fedoraxterm.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/fedoraxterm.svg

%files
%license COPYING
%doc README.md
%{python3_sitelib}/fedoraxterm/
%{python3_sitelib}/fedoraxterm-*.egg-info/
%{_bindir}/fedoraxterm
%{_datadir}/applications/fedoraxterm.desktop
%{_datadir}/icons/hicolor/scalable/apps/fedoraxterm.svg

%changelog
* Mon Mar 17 2026 FedoraXTerm Contributors <fedoraxterm@example.com> - 1.0.0-1
- Initial release
- Tabbed terminal emulator with VTE
- SSH client with session management
- SFTP file browser
- RDP, VNC, Telnet, serial console support
- Network tools (ping, traceroute, nslookup, port scan)
- SSH tunnel / port-forwarding manager
- Multi-execution (broadcast commands to all terminals)
- Macro recording and playback
- Built-in text editor
