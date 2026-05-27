"""
Regression test for the restart-race hole fixed in 1.8.14-1.

Background: main.run() wraps supervisor startup in a bare `except:` that logs
the exception and used to fall off the end of the function -- so an uncaught
exception (e.g. the initial talk_to_cloud(initial=True) raising
AmplifyCriticalException during a rapid double-restart) made the process exit
0. systemd's Restart=on-failure treats exit 0 as a clean stop, so the agent
stayed `inactive (dead)` instead of being revived.

Fix: main.run() now calls sys.exit(1) in that except block. This test pins the
process-exit contract with systemd: an uncaught exception in the run path must
produce a NON-ZERO exit code. Runs in a subprocess because main.py parses
sys.argv at import time and we need full control over argv + the import graph.
"""

import os
import subprocess
import sys
import textwrap

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_uncaught_exception_in_run_exits_nonzero():
    """supervisor.run() raising AmplifyCriticalException -> process exits non-zero.

    The repro forces the foreground branch (so supervisor.run() is called
    directly, no daemon double-fork), stubs out the configtest/cloud-wait gate
    and the context, and installs a Supervisor whose run() raises. With the fix
    the process exits 1; without it main.run() returns and the trailing
    sys.exit(0) marks the bug (test then fails on the != 0 assertion).
    """
    repro = textwrap.dedent(
        """
        import sys
        # main.py parses sys.argv at import time -- set it before importing.
        sys.argv = ['nginx-amplify-agent.py', 'start']

        from gevent import monkey
        monkey.patch_all()

        try:
            from unittest import mock
            import amplify.agent.main as main
            from amplify.agent.common.errors import AmplifyCriticalException

            # foreground branch calls supervisor.run() directly (no fork)
            main.options.foreground = True
            # bypass the configtest / wait-for-cloud gate
            main.test_configuration_and_enviroment = lambda *a, **k: 0

            # neutralise context.setup() / context.default_log
            import amplify.agent.common.context as ctx
            ctx.context = mock.MagicMock()

            # Supervisor whose run() raises the critical exception
            import amplify.agent.supervisor as sup
            class _BoomSupervisor:
                def __init__(self, **kwargs):
                    pass
                def run(self):
                    raise AmplifyCriticalException()
            sup.Supervisor = _BoomSupervisor
        except Exception:
            import traceback
            traceback.print_exc()
            sys.exit(42)  # distinct: setup broke, not the behaviour under test

        print('SETUP_OK', flush=True)
        main.run('amplify')
        # Reaching here means run() returned cleanly -> the bug. Exit 0 so the
        # test's `!= 0` assertion fails loudly.
        sys.exit(0)
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", repro],
        capture_output=True,
        cwd=REPO_ROOT,
        timeout=30,
    )
    stdout = result.stdout.decode()
    stderr = result.stderr.decode()
    assert "SETUP_OK" in stdout, f"repro setup failed before exercising main.run; stderr={stderr!r}"
    assert result.returncode != 0, (
        "main.run() must exit non-zero on an uncaught exception so "
        f"Restart=on-failure revives the agent; got exit 0. stderr={stderr!r}"
    )
    assert result.returncode != 42, f"repro setup error: stderr={stderr!r}"
