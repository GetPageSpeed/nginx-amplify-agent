import os
import re


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


PS_CMD = "ps xao pid,ppid,command | grep 'php-fpm[:]'"


_PS_REGEX = re.compile(r"\s*(?P<pid>\d+)\s+(?P<ppid>\d+)\s+(?P<cmd>.+)\s*")


def PS_PARSER(ps_line):
    # parse ps response line...examples::
    #    36     1 php-fpm: master process (/etc/php/7.0/fpm/php-fpm.conf)
    #    37    36 php-fpm: pool www
    #    38    36 php-fpm: pool www
    parsed = _PS_REGEX.match(ps_line)

    if not parsed:
        return None

    pid, ppid, cmd = int(parsed.group("pid")), int(parsed.group("ppid")), parsed.group("cmd").rstrip()
    return pid, ppid, cmd


_PS_MASTER_REGEX = re.compile(r".*\((?P<conf_path>\/[^\)]*)\).*")


def MASTER_PARSER(ps_master_cmd):
    # parse ps master cmd line...:
    #   php-fpm: master process (/etc/php/7.0/fpm/php-fpm.conf)
    parsed = _PS_MASTER_REGEX.match(ps_master_cmd)

    if not parsed:
        return None

    conf_path = parsed.group("conf_path")
    return conf_path


LS_CMD = "ls -la /proc/%s/exe"
LS_CMD_FREEBSD = "ls -la /proc/%s/file"


_LS_REGEX = re.compile(r".+\-\>\s*(?P<bin_path>.+)\s*")


def LS_PARSER(ls_cmd_line):
    # parse ls cmd line...:
    #   lrwxrwxrwx 1 root root 0 Oct  8 07:09 /proc/2508/exe -> /usr/sbin/php5-fpm
    # or
    #   lrwxrwxrwx 1 root root 0 Mar 31 15:21 /proc/41/exe -> /usr/sbin/php-fpm7.0
    parsed = _LS_REGEX.match(ls_cmd_line)

    if not parsed:
        return None

    return parsed.group("bin_path")


def READLINK_BIN(pid):
    """
    Resolve /proc/<pid>/exe without a subprocess. Returns None when the link
    is unreadable: the agent runs as an unprivileged user and cannot read a
    root-owned master's exe, which is the common case.
    """
    try:
        return os.readlink("/proc/%s/exe" % pid)
    except OSError:
        return None


def IS_PHP_BIN(path):
    return bool(path) and "php" in os.path.basename(path).lower()


_CONF_CANDIDATES = (
    # Remi SCL: /etc/opt/remi/php74/php-fpm.conf
    (re.compile(r"^/etc/opt/remi/(php\d+)/"), ["/opt/remi/%(1)s/root/usr/sbin/php-fpm"]),
    # Software Collections: /etc/opt/rh/rh-php73/php-fpm.conf
    (re.compile(r"^/etc/opt/rh/([\w-]+)/"), ["/opt/rh/%(1)s/root/usr/sbin/php-fpm"]),
    # Debian/Ubuntu: /etc/php/8.1/fpm/php-fpm.conf
    (re.compile(r"^/etc/php/(\d+\.\d+)/fpm/"), ["/usr/sbin/php-fpm%(1)s"]),
    # Plesk: /opt/plesk/php/8.3/etc/php-fpm.conf
    (re.compile(r"^/opt/plesk/php/(\d+\.\d+)/"), ["/opt/plesk/php/%(1)s/sbin/php-fpm"]),
    # cPanel EA: /opt/cpanel/ea-php81/root/etc/php-fpm.conf
    (re.compile(r"^(/opt/cpanel/ea-php\d+/root)/"), ["%(1)s/usr/sbin/php-fpm"]),
    # Base EL / source installs
    (re.compile(r"^/etc/php-fpm\.conf$"), ["/usr/sbin/php-fpm"]),
    (re.compile(r"^/usr/local/etc/php-fpm\.conf$"), ["/usr/local/sbin/php-fpm"]),
)


def CONF_BIN_CANDIDATES(conf_path):
    """
    Binaries that conventionally pair with a php-fpm config path, used when
    /proc/<pid>/exe is unreadable. Callers must check the file exists.
    """
    out = []
    for regex, templates in _CONF_CANDIDATES:
        m = regex.match(conf_path or "")
        if m:
            subs = dict(("%d" % (i + 1), g) for i, g in enumerate(m.groups()))
            out.extend(t % subs for t in templates)
    return out
