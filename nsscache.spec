Summary: Asynchronously synchronise local NSS databases with remote directory services
Name: nsscache
Version: 0.8.3
Release: 1
License: GPLv2
Group: System Environment/Base
Packager: Oliver Hookins <oliver.hookins@anchor.com.au>

URL: http://code.google.com/p/nsscache/
Source: http://nsscache.googlecode.com/files/%{name}-%{version}.tar.gz

Requires: python, python-ldap
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildArchitectures: noarch
BuildRequires: python, python-ldap

%description
nsscache is a Python library and a commandline frontend to that library that
synchronises a local NSS cache against a remote directory service, such as
LDAP.

%prep
%setup -q

%build
CFLAGS="%{optflags}" %{__python} setup.py build

%install
%{__rm} -rf %{buildroot}
%{__python} setup.py install --root="%{buildroot}" --prefix="%{_prefix}"

%clean
%{__rm} -rf %{buildroot}

%files
%defattr(-, root, root, 0755)
%config /etc/nsscache.conf
%exclude /usr/bin/runtests.*
/usr/bin/nsscache
/usr/lib/python2.6/site-packages/nss_cache/

%changelog
* Tue Jan 06 2009 Oliver Hookins <oliver.hookins@anchor.com.au> - 0.8.3-1
- Initial packaging
