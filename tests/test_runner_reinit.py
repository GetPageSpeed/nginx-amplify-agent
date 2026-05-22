"""
Regression tests for the gevent-after-fork race in Runner.do_action().

Background: nginx-amplify-agent.py calls gevent.monkey.patch_all() at module
load, then main.py runs configtest (a network POST through requests, now
gevent-patched) in the parent process. Runner.do_action() then invokes
daemon.DaemonContext which double-forks. The child inherits a gevent hub
whose libev wakefd/eventfd were closed during fork; the supervisor's first
network call raises gevent.hub.LoopExit("This operation would block forever").

Fix shipped in 1.8.11-1: call gevent.reinit() in the child immediately after
DaemonContext enters and before self.app.run(). gevent.reinit() rebuilds the
libev loop (hub.loop.reinit() -> libev ev_loop_fork) and runs _on_fork on the
threadpool/resolver. See https://www.gevent.org/api/gevent.html#gevent.reinit
"""

import os
import subprocess
import sys
import textwrap
from unittest import mock

import pytest

from amplify.agent.common.runner import Runner


def test_do_action_calls_reinit_inside_context_before_app_run():
    """Ordering invariant: enter daemon context, then reinit, then app.run.

    Three orderings are wrong and this test rejects all of them:
    - reinit removed entirely
    - reinit called outside (before) the daemon context
    - reinit called after app.run()
    """
    call_log = []

    daemon_ctx = mock.MagicMock()
    daemon_ctx.__enter__ = mock.MagicMock(side_effect=lambda: call_log.append("enter_context") or daemon_ctx)
    daemon_ctx.__exit__ = mock.MagicMock(side_effect=lambda *a: call_log.append("exit_context") or False)

    app = mock.MagicMock()
    app.run = mock.MagicMock(side_effect=lambda: call_log.append("app.run"))

    runner = Runner.__new__(Runner)  # bypass __init__ which opens real FDs
    runner.app = app
    runner.daemon_context = daemon_ctx

    with mock.patch("amplify.agent.common.runner.gevent.reinit") as reinit:
        reinit.side_effect = lambda: call_log.append("reinit")
        runner.do_action()

    assert call_log == ["enter_context", "reinit", "app.run", "exit_context"], (
        f"reinit must run inside the daemon context and BEFORE app.run; " f"got order: {call_log}"
    )


@pytest.mark.skipif(not hasattr(os, "fork"), reason="fork required")
def test_gevent_reinit_repairs_child_hub_after_fork():
    """End-to-end: parent warms the hub, forks, child calls reinit and uses
    gevent successfully.

    Runs in a subprocess so pytest's own gevent hub state stays isolated.
    Pins the deterministic-success property of the fix: if gevent.reinit()
    ever stops repairing the hub post-fork (gevent break, libev API change),
    this fails. We don't test the without-reinit-fails path because the bug
    isn't reliably reproducible across hosts/kernels and that would flake.
    """
    repro = textwrap.dedent(
        """
        import os, sys, time
        from gevent import monkey
        monkey.patch_all()
        import gevent
        import gevent.hub

        # Parent: warm the hub with a real I/O op (analogous to the
        # configtest POST that happens in main.py before do_action()).
        gevent.spawn(time.sleep, 0.001).join()

        pid = os.fork()
        if pid == 0:
            # Child: this is what runner.py:do_action() now does after
            # DaemonContext closes the parent's FDs.
            gevent.reinit()
            try:
                g = gevent.spawn(time.sleep, 0.01)
                g.join(timeout=3)
                if not g.successful():
                    os._exit(2)
                os._exit(0)
            except gevent.hub.LoopExit:
                os._exit(3)
            except BaseException:
                os._exit(4)
        else:
            _, status = os.waitpid(pid, 0)
            sys.exit(os.WEXITSTATUS(status))
    """
    )
    result = subprocess.run(
        [sys.executable, "-c", repro],
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0, f"child failed with exit {result.returncode}; " f"stderr={result.stderr.decode()!r}"
