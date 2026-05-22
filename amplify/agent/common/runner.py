import signal

import daemon
import gevent
from daemon.pidfile import PIDLockFile

from amplify.agent.common.context import context

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Andrei Belov"
__email__ = "a.belov@f5.com"


class Runner:
    def __init__(self, app):
        def cleanup(signum, frame):
            app.stop()

        self.daemon_context = daemon.DaemonContext()

        self.app = app
        self.daemon_context.detach_process = True
        self.daemon_context.pidfile = PIDLockFile("/var/run/amplify-agent/amplify-agent.pid")
        self.daemon_context.files_preserve = context.get_file_handlers()
        self.daemon_context.signal_map = {signal.SIGTERM: cleanup}
        self._open_streams_from_app_stream_paths(app)

    def _open_streams_from_app_stream_paths(self, app):
        self.daemon_context.stdin = open(app.stdin_path)
        self.daemon_context.stdout = open(app.stdout_path, "w+t")
        self.daemon_context.stderr = open(app.stderr_path, "w+t")

    def do_action(self):
        """
        Enter the daemon context (double-fork) and run the supervisor.

        python-daemon's DaemonContext double-forks via os.fork captured at
        import time, before our monkey-patch ran, so gevent's auto-reinit on
        gevent.os.fork() never fires. Without an explicit reinit() the child
        inherits a hub whose libev wakefd/eventfd were closed during fork;
        the first network call from the supervisor raises
        gevent.hub.LoopExit("This operation would block forever").

        Manifests at cold boot on EL7 where kernel FD allocation is dense
        and gets reused after fork. Warm restarts get scattered FDs and
        usually escape the race.

        See: https://www.gevent.org/api/gevent.html#gevent.reinit
        """
        with self.daemon_context:
            gevent.reinit()
            self.app.run()
