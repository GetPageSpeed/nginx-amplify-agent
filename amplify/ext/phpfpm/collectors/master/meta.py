import os

from amplify.agent.common.context import context
from amplify.agent.data.eventd import INFO
from amplify.agent.collectors.abstract import AbstractMetaCollector
from amplify.agent.common.util import subp, host
from amplify.ext.phpfpm.util.packages import find_packages
from amplify.ext.phpfpm.util.ps import LS_CMD, LS_CMD_FREEBSD, LS_PARSER, READLINK_BIN, IS_PHP_BIN, CONF_BIN_CANDIDATES
from amplify.ext.phpfpm.util.version import VERSION_PARSER


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class PHPFPMMetaCollector(AbstractMetaCollector):
    """
    Meta collector.  Collects meta data about master
    """

    short_name = "phpfpm_meta"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._bin_path = None  # cache for bin_path discovery
        self._version = None  # cache for version discovery
        self._version_line = None  # "" "" ""
        self._packages = None  # {name: version-release} owning the binary
        self._bin_stamp = None  # (inode, mtime) the version cache belongs to

        self.register(self.bin_path, self.version)

    @property
    def default_meta(self):
        meta = {
            "type": self.object.type,
            "root_uuid": context.uuid,
            "local_id": self.object.local_id,
            "name": self.object.name,
            "display_name": self.object.display_name,
            "cmd": self.object.cmd,
            "conf_path": self.object.conf_path,
            "workers": len(self.object.workers),
            "bin_path": None,
            "version": None,
            "version_line": None,
            "packages": None,
        }

        if not self.in_container:
            meta["pid"] = self.object.pid

        return meta

    def _find_bin_path(self):
        """
        Resolve the php-fpm binary. /proc/<pid>/exe of the root-owned master
        is unreadable for the unprivileged agent, so try every worker (often
        running as the agent's user), then the binary that conventionally
        pairs with the master's config path. Anything whose name is not PHP
        is rejected rather than `--version`-ed.
        """
        for pid in [self.object.pid] + list(self.object.workers):
            path = READLINK_BIN(pid)
            if path is None:
                path = self._ls_bin_path(pid)
            if path and path.endswith(" (deleted)"):
                # binary replaced by an upgrade; the new file sits at the path
                path = path[: -len(" (deleted)")]
            if IS_PHP_BIN(path):
                return path

        for candidate in CONF_BIN_CANDIDATES(self.object.conf_path):
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return None

    def _ls_bin_path(self, pid):
        ls_cmd_template = LS_CMD_FREEBSD if host.linux_name() == "freebsd" else LS_CMD
        try:
            ls, _ = subp.call(ls_cmd_template % pid)
            return LS_PARSER(ls[0])
        except Exception as e:
            context.log.debug(f"failed to read php-fpm bin via ls for pid {pid} due to {e.__class__.__name__}")
            return None

    def bin_path(self):
        """
        Compute the bin_path as part of meta collection to be more tolerant of
        users that utilize `pm.ondemand`. bin_path is also not required for
        our regular running logic so it can safely be moved down a level (to
        this collector that runs on a regular async basis).
        """
        if self._bin_path is None:
            self._bin_path = self._find_bin_path()
            if self._bin_path is None:
                context.log.debug("failed to find php-fpm bin path for master pid %s" % self.object.pid)
                # If there is a root_object defined, send an event to the cloud
                if context.objects.root_object:
                    context.objects.root_object.eventd.event(level=INFO, message="php-fpm bin not found")

        self.meta["bin_path"] = self._bin_path

    def version(self):
        """
        Version and owning package of the binary. Recomputed whenever the
        binary file changes: a package upgrade followed by a php-fpm reload
        re-execs the master under the same pid, so pid-based caching would
        report the old version forever.
        """
        if self._bin_path is not None:
            try:
                st = os.stat(self._bin_path)
                stamp = (st.st_ino, st.st_mtime)
            except OSError:
                stamp = None
            if self._version is None or stamp != self._bin_stamp:
                self._version, self._version_line = VERSION_PARSER(self._bin_path)
                self._packages = find_packages(self._bin_path) if self._version else None
                self._bin_stamp = stamp

        self.meta["version"] = self._version
        self.meta["version_line"] = self._version_line
        self.meta["packages"] = self._packages
