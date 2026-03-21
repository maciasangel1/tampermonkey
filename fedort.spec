%global pypi_name fedort

Name:           fedort
Version:        1.0.0
Release:        1%{?dist}
Summary:        SecureCRT-compatible terminal emulator and SSH client for Fedora Linux

License:        GPL-3.0-or-later
URL:            https://github.com/fedort/fedort
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
FedoRT is a SecureCRT-compatible terminal emulator and SSH client
built for Fedora Linux. It provides tabbed sessions, SSH/SFTP connectivity,
session management, and a customizable interface using GTK 3 and VTE.

%prep
%autosetup -n %{pypi_name}-%{version}

%build
%py3_build

%install
%py3_install

# Desktop file
install -Dm644 fedort/resources/fedort.desktop \
    %{buildroot}%{_datadir}/applications/fedort.desktop
desktop-file-validate %{buildroot}%{_datadir}/applications/fedort.desktop

# Icon
install -Dm644 fedort/resources/fedort.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/fedort.svg

%files
%license COPYING
%doc README.md
%{python3_sitelib}/%{pypi_name}/
%{python3_sitelib}/%{pypi_name}-*.egg-info/
%{_bindir}/fedort
%{_bindir}/fedort-gui
%{_datadir}/applications/fedort.desktop
%{_datadir}/icons/hicolor/scalable/apps/fedort.svg

%changelog
* Mon Jan 01 2025 FedoRT Contributors <fedort@example.com> - 1.0.0-1
- Initial package
