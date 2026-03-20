%global pypi_name fedoraxterm

Name:           fedoraxterm
Version:        1.0.0
Release:        1%{?dist}
Summary:        SecureCRT-compatible terminal emulator and SSH client for Fedora Linux

License:        GPL-3.0-or-later
URL:            https://github.com/fedoraxterm/fedoraxterm
Source0:        %{pypi_source}

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  desktop-file-utils

Requires:       python3-gobject >= 3.42
Requires:       python3-paramiko >= 3.0
Requires:       python3-cryptography >= 42.0.4
Requires:       gtk3
Requires:       vte291
Requires:       openssh-clients

%description
FedoraXTerm is a SecureCRT-compatible terminal emulator and SSH client
built for Fedora Linux. It provides tabbed sessions, SSH/SFTP connectivity,
session management, and a customizable interface using GTK 3 and VTE.

%prep
%autosetup -n %{pypi_name}-%{version}

%build
%py3_build

%install
%py3_install

# Desktop file
install -Dm644 fedoraxterm/resources/fedoraxterm.desktop \
    %{buildroot}%{_datadir}/applications/fedoraxterm.desktop
desktop-file-validate %{buildroot}%{_datadir}/applications/fedoraxterm.desktop

# Icon
install -Dm644 fedoraxterm/resources/fedoraxterm.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/fedoraxterm.svg

%files
%license COPYING
%doc README.md
%{python3_sitelib}/%{pypi_name}/
%{python3_sitelib}/%{pypi_name}-*.egg-info/
%{_bindir}/fedoraxterm
%{_bindir}/fedoraxterm-gui
%{_datadir}/applications/fedoraxterm.desktop
%{_datadir}/icons/hicolor/scalable/apps/fedoraxterm.svg

%changelog
* Mon Jan 01 2025 FedoraXTerm Contributors <fedoraxterm@example.com> - 1.0.0-1
- Initial package
