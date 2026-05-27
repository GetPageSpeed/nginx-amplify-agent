%define nginx_home %{_localstatedir}/cache/nginx
%define nginx_user nginx
%define nginx_group nginx
%define _python_bytecompile_errors_terminate_build 0

# Define flag for systems that need binary wheels (older Python 3.6/3.7)
# EL7/EL8 have Python 3.6
%if 0%{?rhel} >= 7 && 0%{?rhel} <= 8
%global _need_binary_wheels 1
%endif

Summary: GetPageSpeed Amplify Agent
Name: nginx-amplify-agent
Version: %%AMPLIFY_AGENT_VERSION%%
Release: %%AMPLIFY_AGENT_RELEASE%%%{?dist}
Vendor: GetPageSpeed <info@getpagespeed.com>
Group: System Environment/Daemons
URL: https://github.com/GetPageSpeed/nginx-amplify-agent
License: 2-clause BSD-like license

Source0: nginx-amplify-agent-%{version}.tar.gz
Source1: nginx-amplify-agent.service

BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root

BuildRequires: python3-devel
BuildRequires: python3-pip
BuildRequires: python3-setuptools
BuildRequires: systemd-rpm-macros

# Filter out auto-generated requires for bundled Python packages
# These packages are vendored into amplify/ directory during build
%global __requires_exclude_from ^%{python3_sitelib}/amplify/.*$

%if 0%{?amzn} >= 2
Requires: python3 >= 3.7
Requires: python3-requests
%endif

%if 0%{?rhel} == 8
Requires: python3 >= 3.6
Requires: python3-requests
%endif

%if 0%{?rhel} >= 9
Requires: python3 >= 3.9
Requires: python3-requests
# netifaces and psutil are bundled via pip install --target
%endif

Requires: initscripts >= 8.36
Requires(post): chkconfig

%if 0%{?rhel} >= 8 || 0%{?fedora}
%define _debugsource_template %{nil}
%undefine _missing_build_ids_terminate_build
%endif


%description
The GetPageSpeed Amplify Agent is a small, Python application that
provides system and NGINX metric collection. It is part of
GetPageSpeed Amplify - the monitoring and configuration assistance
service for NGINX.
This package installs and runs GetPageSpeed Amplify Agent daemon.
See https://amplify.getpagespeed.com for more information


%prep
%setup -q -n nginx-amplify-agent-%{version}
%{__cp} -p %{SOURCE0} .


%build
# For EL7/EL8/SLES15, upgrade pip first to get proper wheel support, and force binary packages
# to avoid build issues with setuptools_scm on Python 3.6
%if 0%{?_need_binary_wheels}
%{__python3} -m pip install --upgrade pip
%{__python3} -m pip install --upgrade --target=amplify --no-compile --only-binary=ujson,greenlet -r %%REQUIREMENTS%%
%else
%{__python3} -m pip install --upgrade --target=amplify --no-compile -r %%REQUIREMENTS%%
%endif
# Install zope.event which is required by gevent but not always pulled in as a dependency
# See https://github.com/pypa/pip/issues/10629
%{__python3} -m pip install --upgrade --target=amplify_ --no-compile zope.event
%{__cp} -Pr amplify_/zope* amplify/
%{__python3} setup.py build


%pre
# Add the "nginx" user
getent group %{nginx_group} >/dev/null || groupadd -r %{nginx_group}
getent passwd %{nginx_user} >/dev/null || \
    useradd -r -g %{nginx_group} -s /sbin/nologin \
    -d %{nginx_home} -c "nginx user"  %{nginx_user}
exit 0


%install
%define python_libexec /usr/bin/
[ "%{buildroot}" != "/" ] && rm -rf %{buildroot}
%{__python3} -c 'import setuptools; exec(open("setup.py").read())' install -O1 --skip-build --install-scripts %{python_libexec} --root %{buildroot}
mkdir -p %{buildroot}/var/
mkdir -p %{buildroot}/var/log/
mkdir -p %{buildroot}/var/log/amplify-agent/
mkdir -p %{buildroot}/var/
mkdir -p %{buildroot}/var/run/
mkdir -p %{buildroot}/var/run/amplify-agent/
%{__mkdir} -p %{buildroot}/%{_unitdir}
%{__install} -m644 %SOURCE1 %{buildroot}/%{_unitdir}/amplify-agent.service


%clean
[ "%{buildroot}" != "/" ] && rm -rf %{buildroot}


%files
%define config_files /etc/amplify-agent/
%defattr(-,root,root,-)
%{python3_sitelib}/*
%{python_libexec}/*
%{config_files}/*
%attr(0755,nginx,nginx) %dir /var/log/amplify-agent
%attr(0755,nginx,nginx) %dir /var/run/amplify-agent
%{_unitdir}/amplify-agent.service
/etc/init.d/amplify-agent
/etc/logrotate.d/amplify-agent


%post
if [ $1 -eq 1 ] ; then
    /usr/bin/systemctl preset amplify-agent.service >/dev/null 2>&1 ||:
    /usr/bin/systemctl enable amplify-agent.service >/dev/null 2>&1 ||:
    mkdir -p /var/run/amplify-agent
    touch /var/log/amplify-agent/agent.log
    chown nginx /var/run/amplify-agent /var/log/amplify-agent/agent.log
elif [ $1 -eq 2 ] ; then
    %define agent_conf_file /etc/amplify-agent/agent.conf

    if [ ! -f "%{agent_conf_file}" ]; then
        exit 0
    fi

    # Check for an older version of the agent running
    if command -V pgrep > /dev/null 2>&1; then
        agent_pid=`pgrep amplify-agent || true`
    else
        agent_pid=`ps aux | grep -i '[a]mplify-agent' | awk '{print $2}'`
    fi

    # stop it
    if [ -n "$agent_pid" ]; then
        service amplify-agent stop > /dev/null 2>&1 < /dev/null
    fi

    # Change API URL to GetPageSpeed Amplify
    sh -c "sed -i.old 's/api_url.*$/api_url = https:\/\/amplify.getpagespeed.com:443\/1.4/' \
        %{agent_conf_file}"

    # Add PHP-FPM to config file
    if ! grep -i phpfpm "%{agent_conf_file}" > /dev/null 2>&1 ; then
        sh -c "echo >> %{agent_conf_file}" && \
        sh -c "echo '[extensions]' >> %{agent_conf_file}" && \
        sh -c "echo 'phpfpm = True' >> %{agent_conf_file}"
    fi

    # restart it if it was stopped before
    if [ -n "$agent_pid" ]; then
        service amplify-agent start > /dev/null 2>&1 < /dev/null
    fi
fi


%preun
if [ $1 -eq 0 ]; then
    /usr/bin/systemctl --no-reload disable amplify-agent.service >/dev/null 2>&1 ||:
    /usr/bin/systemctl stop amplify-agent.service >/dev/null 2>&1 ||:
fi


%changelog
* Thu May 28 2026 GetPageSpeed <info@getpagespeed.com> 1.8.14-1
- 1.8.14-1
- Close a restart-recovery hole. An uncaught exception during agent startup
  (notably the initial talk_to_cloud raising AmplifyCriticalException when a
  rapid restart races the cloud handshake) was logged and then let the process
  fall off the end of run() and exit 0. systemd Restart=on-failure treats a
  clean exit as success, so the agent stayed inactive (dead) instead of being
  revived; a single manual start recovered it. main.run() now exits non-zero on
  any uncaught run-time exception, so the existing on-failure net (1.8.12-1)
  restarts it -- and the fresh process re-runs gevent.reinit() (1.8.11-1).
- Stop two destructors (AbstractManager.__del__, FileTail.__del__) from raising
  during garbage collection / interpreter shutdown -- a missing `running`
  attribute and a None context.log surfaced as unraisable-exception warnings.
* Wed May 27 2026 GetPageSpeed <info@getpagespeed.com> 1.8.13-1
- 1.8.13-1
- Stop the recurring "workers_io raised AccessDenied" log noise. The NGINX
  worker IO collector reads /proc/<pid>/io, which is ptrace-gated and
  unreadable for the root-owned master (and even between same-user workers),
  so io_counters() raised psutil.AccessDenied and aborted the whole collection
  cycle, zeroing nginx.workers.io.kbs_r/kbs_w. Now skip the inaccessible
  process and sum IO over the readable workers. NoSuchProcess still propagates
  to the need_restart path.
* Wed May 27 2026 GetPageSpeed <info@getpagespeed.com> 1.8.12-1
- 1.8.12-1
- systemd auto-restart safety net for the cold-boot start path. The
  gevent.reinit() fix in 1.8.11-1 is the cure for the EL7 fork race; this
  guarantees recovery if it ever loses the race on some cold-boot FD timing.
  Adds Restart=on-failure, RestartSec=5s, StartLimitInterval=60,
  StartLimitBurst=3 to the unit (pre-v230 names in [Service] for EL7
  systemd 219). on-failure does not fight a clean `systemctl stop`; the
  bounded limit lets a transient boot race recover on retry yet still
  surfaces a persistent failure as `failed` instead of looping forever.

* Fri May 22 2026 GetPageSpeed <info@getpagespeed.com> 1.8.11-1
- 1.8.11-1
- Fix "This operation would block forever" race on EL7 cold-boot start.
  python-daemon's DaemonContext double-forks via os.fork captured at
  import time -- before our gevent.monkey.patch_all() ran -- so gevent's
  auto-reinit-on-fork never fires. The child process inherited a hub
  whose libev wakefd/eventfd were closed during fork, and the
  supervisor's first network call raised
  gevent.hub.LoopExit("This operation would block forever").
  Call gevent.reinit() in the child immediately after DaemonContext
  enters to rebuild the libev hub. Manifested at cold boot on EL7;
  warm restarts got scattered FD numbers and usually escaped the race.

* Tue May 19 2026 GetPageSpeed <info@getpagespeed.com> 1.8.10-1
- 1.8.10-1
- (DEB-only fix, no behavior change on RPM.) Follow-up to 1.8.9-1
  after the test-deb-reinstall-recovery integration test caught two
  more bugs on jammy:
  * override_dh_installdeb in debian/rules strips agent.conf.default
    from the auto-detected conffiles list. The 1.8.9-1 attempt used a
    .conffiles file, but that APPENDS to auto-detection rather than
    replacing it.
  * postinst no longer early-exits on the upgrade branch when
    agent.conf is missing -- the early exit was skipping
    dh_installsystemd's unmask, so a service masked by `apt-get remove`
    stayed masked through reinstall and install.sh's "Launching" step
    failed.
- (Cross-distro) install.sh self-heal branch added in 1.8.9-1 has been
  removed -- redundant once 1.8.10-1 is the latest available package.

* Tue May 19 2026 GetPageSpeed <info@getpagespeed.com> 1.8.9-1
- 1.8.9-1
- install.sh self-heals a missing /etc/amplify-agent/agent.conf.default
  after package install (yum reinstall on RPM, apt-get install --reinstall
  --force-confmiss on DEB). Closes a customer-reported "can't find
  /etc/amplify-agent/agent.conf.default" abort on Ubuntu 22.04 after a
  remove + rm /etc/amplify-agent + reinstall cycle.
- DEB-only: agent.conf.default is no longer registered as a dpkg conffile
  (it is a build-time template for install.sh, not a user-editable config).
  No behavior change on RPM, since the spec lists %{config_files}/* without
  %config(noreplace).

* Sat May 16 2026 GetPageSpeed <info@getpagespeed.com> 1.8.5-2
- 1.8.5-2
- Fix TypeError in exponential_delay() on Python 3.12+ (Noble/Trixie/EL10/Fedora/SLES16)
- Ported from upstream PR github.com/nginxinc/nginx-amplify-agent/pull/125 by @jasil1414

* Thu May 14 2026 GetPageSpeed <info@getpagespeed.com> 1.8.5-1
- 1.8.5-1
- Agent now starts when agent.conf lacks the optional [loggers]/[handlers]/[formatters] sections (falls back to built-in logging defaults)
- systemd unit Documentation URL points to amplify.getpagespeed.com/docs

* Wed Jan 29 2025 GetPageSpeed <info@getpagespeed.com> 1.8.4-3
- 1.8.4-3
- Update version in all setup.py files

* Wed Jan 29 2025 GetPageSpeed <info@getpagespeed.com> 1.8.4-2
- 1.8.4-2
- Fix RPM auto-requires filtering for bundled Python packages on EL10

* Wed Jan 29 2025 GetPageSpeed <info@getpagespeed.com> 1.8.4-1
- 1.8.4-1
- Replace asyncore with selectors for Python 3.12+ compatibility
- Add GitHub Actions CI with Python 3.8-3.13 test matrix

* Wed Jan 29 2025 GetPageSpeed <info@getpagespeed.com> 1.8.3-3
- 1.8.3-3
- Fix CI build configuration

* Tue Jan 28 2025 GetPageSpeed <info@getpagespeed.com> 1.8.3-2
- 1.8.3-2
- Rebranded for GetPageSpeed Amplify
- Updated API URL to amplify.getpagespeed.com

* Wed Jan  8 2025 Andrei Belov <a.belov@f5.com> 1.8.3-1
- 1.8.3-1
- migrated to the most recent daemonizing logic (PEP 3143)

* Mon May 27 2024 Andrei Belov <a.belov@f5.com> 1.8.2-1
- 1.8.2-1
- pyMySQL updated to 1.1.1
- requests updated to 2.32.2

* Fri Sep 23 2022 Andrei Belov <a.belov@f5.com> 1.8.1-1
- 1.8.1-1
- crossplane updated to 0.5.8
- fixed parsing of non-Unicode nginx configurations

* Tue Mar 29 2022 Bill Beckelhimer <w.beckelhimer@f5.com> 1.8.0-2
- 1.8.0-2
- bug fixes
- update dependency

* Thu Dec  9 2021 Andrei Belov <defan@nginx.com> 1.8.0-1
- 1.8.0-1
- agent version for Python 3

* Mon Sep 23 2019 Andrei Belov <defan@nginx.com> 1.7.0-5
- improved nginx-plus status URL discovery method
- updated crossplane, psutil, and requests modules
- init script fixed for Debian 10 "buster"

* Thu Mar 28 2019 Andrei Belov <defan@nginx.com> 1.7.0-4
- 1.7.0-4
- fixed agent's user auto-detection

* Thu Nov 15 2018 Grant Hulegaard <grant.hulegaard@nginx.com> 1.7.0-1
- 1.7.0-1
- Various bug fixes

* Thu Sep 20 2018 Grant Hulegaard <grant.hulegaard@nginx.com> 1.6.0-1
- 1.6.0-1
- Added support for log formats with new line characters
- Various bug fixes

* Thu Sep  6 2018 Raymond Lau <raymond.lau@nginx.com> 1.5.0-1
- 1.5.0-1
- Various bug fixes

* Thu Jul 26 2018 Mike Belov <dedm@nginx.com> 1.4.1-1
- 1.4.1-1
- Various bug fixes

* Fri Jun  8 2018 Grant Hulegaard <grant.hulegaard@nginx.com> 1.4.0-1
- 1.4.0-1
- New metrics for nginx, phpfpm, and mysql status
- Support monitoring of remote MySQL instances
- Added LAUNCHERS as a configurable parameter in the Agent config
- Various renaming of files and variables
- Various bug fixes

* Thu May 10 2018 Mike Belov <dedm@nginx.com> 1.3.0-1
- 1.3.0-1
- New nginx metric: number of config reloads, cache max size
- Improvements to extension interface
- Improved nginx log detection
- Additional config reporting
- MySQL extension fixes and improvements
- Various bug fixes

* Thu Apr  5 2018 Mike Belov <dedm@nginx.com> 1.2.0-1
- 1.2.0-1
- NGINX+ API support
- Ability to store UUID in the config file (if needed)
- Upgraded NGINX Crossplane parser
- Improved nginx logs parsing

* Wed Feb  7 2018 Mike Belov <dedm@nginx.com> 1.1.0-1
- 1.1.0-1
- MySQL monitoring support
- Improved nginx logs parsing
- Various bug fixes

* Tue Jan 16 2018 Mike Belov <dedm@nginx.com> 1.0.1-2
- 1.0.1-2
- Postinst script fix

* Tue Jan  9 2018 Mike Belov <dedm@nginx.com> 1.0.1-1
- 1.0.1-1
- UUID bug fix

* Tue Dec 26 2017 Mike Belov <dedm@nginx.com> 1.0.0-1
- 1.0.0-1
- Support for additional NGINX+ objects (streams and slabs)
- NGINX Crossplane is the new config parser
- Updgraded gevent
- Special troubleshooter script
- No longer storing UUID in the config by default
- Various bug fixes

* Wed Oct 18 2017 Grant Hulegaard <grant.hulegaard@nginx.com> 0.47-1
- 0.47-1
- New config parser
- Debug mode
- Bug fix for error logging with PHP-FPM

* Sat Sep 23 2017 Mike Belov <dedm@nginx.com> 0.46-2
- 0.46-2
- Fixes for Centos6

* Thu Sep 21 2017 Grant Hulegaard <grant.hulegaard@nginx.com> 0.46-1
- 0.46-1
- Bug fixes

* Thu Aug 17 2017 Mike Belov <dedm@nginx.com> 0.45-2
- 0.45-2
- Fixes for config parser

* Wed Aug  9 2017 Mike Belov <dedm@nginx.com> 0.45-1
- 0.45-1
- PHP-FPM bug fixes
- Fixes for config parser

* Mon Jun 19 2017 Mike Belov <dedm@nginx.com> 0.44-2
- 0.44-2
- PHP-FPM bug fixes

* Thu Jun 15 2017 Mike Belov <dedm@nginx.com> 0.44-1
- 0.44-1
- PHP-FPM bug fixes

* Thu May 18 2017 Mike Belov <dedm@nginx.com> 0.43-1
- 0.43-1
- PHP-FPM bug fixes
- Memory leak fixes
- Bug fixes

* Mon Apr 17 2017 Mike Belov <dedm@nginx.com> 0.42-2
- 0.42-2
- PHP-FPM bug fixes

* Mon Apr  3 2017 Mike Belov <dedm@nginx.com> 0.42-1
- 0.42-1
- PHP-FPM support
- Tags support
- Memory leak fixes
- Bug fixes

* Thu Jan 19 2017 Mike Belov <dedm@nginx.com> 0.41-2
- 0.41-2
- Updated requests library (fixes some memory leaks)
- Fixes for config and nginx -V parsing

* Thu Jan  5 2017 Mike Belov <dedm@nginx.com> 0.41-1
- 0.41-1
- Generic support for *nix systems
- Fixes for config parser

* Mon Nov  7 2016 Mike Belov <dedm@nginx.com> 0.40-2
- 0.40-2
- Bug fixe8

* Tue Nov  1 2016 Mike Belov <dedm@nginx.com> 0.40-1
- 0.40-1
- Bug fixes
- Syslog support

* Wed Sep 28 2016 Mike Belov <dedm@nginx.com> 0.39-3
- 0.39-3
- Bug fixes

* Wed Sep 21 2016 Mike Belov <dedm@nginx.com> 0.39-2
- 0.39-2
- Bug fixes

* Tue Sep 20 2016 Mike Belov <dedm@nginx.com> 0.39-1
- 0.39-1
- Config parser improvements
- Log parser improvements
- Bug fixes

* Thu Aug 25 2016 Mike Belov <dedm@nginx.com> 0.38-1
- 0.38-1
- FreeBSD support
- Bug fixes

* Thu Jul 28 2016 Mike Belov <dedm@nginx.com> 0.37-1
- 0.37-1
- Bug fixes

* Mon Jul 18 2016 Mike Belov <dedm@nginx.com> 0.36-1
- 0.36-1
- Bug fixes

* Wed Jun 29 2016 Mike Belov <dedm@nginx.com> 0.35-1
- 0.35-1
- New metrics for NGINX+
- Bug fixes

* Wed Jun 22 2016 Mike Belov <dedm@nginx.com> 0.34-2
- 0.34-2
- Bug fixes

* Fri Jun 10 2016 Mike Belov <dedm@nginx.com> 0.34-1
- 0.34-1
- NGINX+ metrics aggregation support
- Bug fixes

* Thu May  5 2016 Mike Belov <dedm@nginx.com> 0.33-3
- 0.33-3
- Bug fixes

* Thu May  5 2016 Mike Belov <dedm@nginx.com> 0.33-2
- 0.33-2
- Bug fixes

* Fri Apr 29 2016 Mike Belov <dedm@nginx.com> 0.33-1
- 0.33-1
- NGINX+ objects support
- Bug fixes

* Wed Apr 13 2016 Mike Belov <dedm@nginx.com> 0.32-1
- 0.32-1
- Bug fixes
- psutil==4.0.0 support

* Thu Mar 31 2016 Mike Belov <dedm@nginx.com> 0.31-1
- 0.31-1
- Bug fixes

* Tue Mar 15 2016 Mike Belov <dedm@nginx.com> 0.30-1
- 0.30-1
- Bug fixes
- Initial SSL analytics support

* Tue Jan 19 2016 Mike Belov <dedm@nginx.com> 0.28-1
- 0.28-1
- Bug fixes
- Amazon Linux support
- Initial NGINX+ extended status support

* Thu Dec 17 2015 Mike Belov <dedm@nginx.com> 0.27-1
- 0.27-1
- Bug fixes

* Thu Dec  3 2015 Mike Belov <dedm@nginx.com> 0.25-1
- 0.25-1
- Bug fixes
- New metric: system.cpu.stolen
- Nginx config parsing improved

* Tue Nov 24 2015 Mike Belov <dedm@nginx.com> 0.24-2
- 0.24-2
- Bug fixes

* Tue Nov 24 2015 Mike Belov <dedm@nginx.com> 0.24-1
- 0.24-1
- Bug fixes

* Wed Nov 18 2015 Mike Belov <dedm@nginx.com> 0.23-1
- 0.23-1
- Bug fixes
- Ubuntu Wily support

* Sun Nov 15 2015 Mike Belov <dedm@nginx.com> 0.22-5
- 0.22-5
- Bug fixes

* Fri Nov 13 2015 Mike Belov <dedm@nginx.com> 0.22-4
- 0.22-4
- Bug fixes

* Thu Nov 12 2015 Mike Belov <dedm@nginx.com> 0.22-3
- 0.22-3
- Bug fixes

* Wed Nov 11 2015 Mike Belov <dedm@nginx.com> 0.22-2
- 0.22-2
- Bug fixes

* Mon Nov  9 2015 Mike Belov <dedm@nginx.com> 0.22-1
- 0.22-1
- Bug fixes

* Thu Nov  5 2015 Mike Belov <dedm@nginx.com> 0.21-3
- 0.21-3
- Additional events added

* Wed Nov  4 2015 Mike Belov <dedm@nginx.com> 0.21-2
- 0.21-2
- Bug fixes

* Mon Nov  2 2015 Mike Belov <dedm@nginx.com> 0.21-1
- 0.21-1
- Bug fixes

* Wed Oct 28 2015 Mike Belov <dedm@nginx.com> 0.20-1
- 0.20-1
- RPM support
