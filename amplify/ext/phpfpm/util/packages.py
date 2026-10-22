"""
Find the OS package that owns the php-fpm binary.

The upstream version alone can't tell a patched backport (GetPageSpeed
7.0.33-43.el7, Debian 8.1.2-1ubuntu2.19) from a vulnerable build of the same
version, so the server needs the package release to judge CVEs.
"""
from amplify.agent.common.context import context
from amplify.agent.common.util import subp


RPM_CMD = "rpm -qf '%s' --queryformat '%%{NAME} %%{VERSION}-%%{RELEASE}\\n'"
DPKG_S_CMD = "dpkg -S '%s'"
DPKG_QUERY_CMD = "dpkg-query -W -f='${Version}' '%s'"


def _rpm(bin_path):
    out, _ = subp.call(RPM_CMD % bin_path, check=False)
    line = out[0].strip() if out else ""
    parts = line.split()
    # "file /x is not owned by any package" / "rpm: command not found"
    if len(parts) != 2 or "not owned" in line:
        return None
    return {parts[0]: parts[1]}


def _dpkg(bin_path):
    out, _ = subp.call(DPKG_S_CMD % bin_path, check=False)
    line = out[0].strip() if out else ""
    # "php8.1-fpm: /usr/sbin/php-fpm8.1"
    if ": " not in line:
        return None
    package = line.split(": ", 1)[0].split(":")[0]  # drop ":amd64"
    ver, _ = subp.call(DPKG_QUERY_CMD % package, check=False)
    version = ver[0].strip() if ver else ""
    if not version:
        return None
    return {package: version}


def find_packages(bin_path):
    """
    :return: {package_name: "version-release"} or None (source build, or no
             package manager the agent can query)
    """
    for finder in (_rpm, _dpkg):
        try:
            found = finder(bin_path)
        except Exception as e:
            context.log.debug(f"php-fpm package lookup {finder.__name__} failed: {e.__class__.__name__}")
            continue
        if found:
            return found
    return None
