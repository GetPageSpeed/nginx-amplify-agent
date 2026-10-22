"""
PHP-FPM master identity: version, binary and owning package.

Agents up to 1.8.18 `--version`-ed whatever /proc/<pid>/exe resolved to and
reported Python (3.6.8) and systemd (239) versions as PHP; as an unprivileged
user they also could not read the root-owned master's exe, so most hosts sent
no version at all. The server needs version + package release to judge PHP
CVEs such as PHP2Shell (CVE-2026-109618/109619).
"""
import os
from unittest import mock

import pytest

from amplify.ext.phpfpm.util import packages, ps, version
from amplify.ext.phpfpm.collectors.master.meta import PHPFPMMetaCollector


@pytest.fixture(autouse=True)
def quiet_context():
    with mock.patch.object(version, "context"), mock.patch.object(packages, "context"):
        yield


def _call_returning(stdout):
    return mock.MagicMock(return_value=(stdout, [""]))


@pytest.mark.parametrize(
    "line,want",
    [
        (
            "PHP 7.4.33 (fpm-fcgi) (built: Oct 22 2026 10:00:00)",
            ("7.4.33", "PHP 7.4.33 (fpm-fcgi) (built: Oct 22 2026 10:00:00)"),
        ),
        (
            "PHP 5.5.9-1ubuntu4.17 (fpm-fcgi) (built: May 19 2016 19:08:26)",
            ("5.5.9", "PHP 5.5.9-1ubuntu4.17 (fpm-fcgi) (built: May 19 2016 19:08:26)"),
        ),
        ("systemd 239 (239-82.el8)", (None, None)),
        ("Python 3.6.8", (None, None)),
        ("", (None, None)),
    ],
)
def test_version_parser_accepts_only_php(line, want):
    with mock.patch.object(version.subp, "call", _call_returning([line])):
        assert version.VERSION_PARSER("/usr/sbin/php-fpm") == want


def test_version_parser_failure_returns_tuple():
    with mock.patch.object(version.subp, "call", side_effect=OSError("boom")):
        assert version.VERSION_PARSER("/usr/sbin/php-fpm") == (None, None)


@pytest.mark.parametrize(
    "conf,want",
    [
        ("/etc/opt/remi/php74/php-fpm.conf", ["/opt/remi/php74/root/usr/sbin/php-fpm"]),
        ("/etc/php/8.1/fpm/php-fpm.conf", ["/usr/sbin/php-fpm8.1"]),
        ("/opt/plesk/php/8.3/etc/php-fpm.conf", ["/opt/plesk/php/8.3/sbin/php-fpm"]),
        ("/etc/php-fpm.conf", ["/usr/sbin/php-fpm"]),
        ("/opt/cpanel/ea-php81/root/etc/php-fpm.conf", ["/opt/cpanel/ea-php81/root/usr/sbin/php-fpm"]),
        ("/srv/custom.conf", []),
        (None, []),
    ],
)
def test_conf_bin_candidates(conf, want):
    assert ps.CONF_BIN_CANDIDATES(conf) == want


def test_is_php_bin_rejects_non_php():
    assert ps.IS_PHP_BIN("/usr/sbin/php-fpm8.1")
    assert ps.IS_PHP_BIN("/opt/remi/php74/root/usr/sbin/php-fpm")
    assert not ps.IS_PHP_BIN("/usr/lib/systemd/systemd")
    assert not ps.IS_PHP_BIN("/usr/bin/python3.6")
    assert not ps.IS_PHP_BIN(None)


def _fake_call(responses):
    def call(cmd, check=True):
        for prefix, out in responses.items():
            if cmd.startswith(prefix):
                return out, [""]
        raise AssertionError("unexpected command %s" % cmd)

    return call


def test_find_packages_rpm():
    with mock.patch.object(packages.subp, "call", _fake_call({"rpm -qf": ["php-fpm 7.0.33-43.el7", ""]})):
        assert packages.find_packages("/usr/sbin/php-fpm") == {"php-fpm": "7.0.33-43.el7"}


def test_find_packages_falls_back_to_dpkg():
    with mock.patch.object(
        packages.subp,
        "call",
        _fake_call(
            {
                "rpm -qf": ["/bin/sh: rpm: command not found", ""],
                "dpkg -S": ["php8.1-fpm: /usr/sbin/php-fpm8.1", ""],
                "dpkg-query": ["8.1.2-1ubuntu2.19"],
            }
        ),
    ):
        assert packages.find_packages("/usr/sbin/php-fpm8.1") == {"php8.1-fpm": "8.1.2-1ubuntu2.19"}


def test_find_packages_source_build():
    with mock.patch.object(
        packages.subp,
        "call",
        _fake_call(
            {
                "rpm -qf": ["file /usr/local/sbin/php-fpm is not owned by any package", ""],
                "dpkg -S": [""],
            }
        ),
    ):
        assert packages.find_packages("/usr/local/sbin/php-fpm") is None


def _collector(pid=10, workers=(11,), conf="/etc/php-fpm.conf"):
    c = PHPFPMMetaCollector.__new__(PHPFPMMetaCollector)
    c.object = mock.MagicMock(pid=pid, workers=list(workers), conf_path=conf)
    c.meta = {}
    c._bin_path = None
    c._version = None
    c._version_line = None
    c._packages = None
    c._bin_stamp = None
    return c


def test_bin_path_skips_unreadable_master_and_non_php(monkeypatch):
    c = _collector(pid=10, workers=(11, 12))
    links = {10: None, 11: "/usr/lib/systemd/systemd", 12: "/usr/sbin/php-fpm (deleted)"}
    monkeypatch.setattr("amplify.ext.phpfpm.collectors.master.meta.READLINK_BIN", links.get)
    monkeypatch.setattr(c, "_ls_bin_path", lambda pid: None)
    assert c._find_bin_path() == "/usr/sbin/php-fpm"


def test_bin_path_falls_back_to_conf_candidate(monkeypatch, tmp_path):
    binary = tmp_path / "php-fpm"
    binary.write_text("")
    binary.chmod(0o755)
    c = _collector(conf="/etc/opt/remi/php74/php-fpm.conf")
    monkeypatch.setattr("amplify.ext.phpfpm.collectors.master.meta.READLINK_BIN", lambda pid: None)
    monkeypatch.setattr(c, "_ls_bin_path", lambda pid: None)
    monkeypatch.setattr(
        "amplify.ext.phpfpm.collectors.master.meta.CONF_BIN_CANDIDATES",
        lambda conf: ["/nonexistent/php-fpm", str(binary)],
    )
    assert c._find_bin_path() == str(binary)


def test_version_recomputed_when_binary_changes(monkeypatch, tmp_path):
    binary = tmp_path / "php-fpm"
    binary.write_text("old")
    c = _collector()
    c._bin_path = str(binary)
    answers = iter([("8.1.29", "PHP 8.1.29 (fpm-fcgi)"), ("8.4.27", "PHP 8.4.27 (fpm-fcgi)")])
    parser = mock.MagicMock(side_effect=lambda path: next(answers))
    monkeypatch.setattr("amplify.ext.phpfpm.collectors.master.meta.VERSION_PARSER", parser)
    monkeypatch.setattr("amplify.ext.phpfpm.collectors.master.meta.find_packages", lambda path: {"php-fpm": "x"})

    c.version()
    c.version()
    assert c.meta["version"] == "8.1.29"
    assert parser.call_count == 1  # unchanged binary: cached

    # package upgrade replaces the file (new inode), php-fpm reload keeps the pid
    os.remove(str(binary))
    binary.write_text("new build")
    c.version()
    assert c.meta["version"] == "8.4.27"
    assert c.meta["version_line"] == "PHP 8.4.27 (fpm-fcgi)"
    assert c.meta["packages"] == {"php-fpm": "x"}
