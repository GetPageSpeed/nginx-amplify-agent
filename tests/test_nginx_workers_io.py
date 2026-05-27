"""
Regression tests for workers_io() gracefully skipping inaccessible processes.

Background: NginxMetricsCollector.workers_io() calls psutil.Process.io_counters()
on every nginx worker. Reading /proc/<pid>/io is ptrace-gated (PTRACE_MODE_READ_FSCREDS,
stricter than a uid match), so it raises psutil.AccessDenied even between same-user
workers and on the root-owned master. The loop only caught psutil.ZombieProcess, so
AccessDenied propagated out and aborted the whole collection cycle -- noisy log
("workers_io raised AccessDenied") and a zeroed nginx.workers.io.kbs_r/kbs_w that cycle.

Fix: catch psutil.AccessDenied per-process and continue, summing IO over the readable
workers. psutil.NoSuchProcess is intentionally NOT caught here -- handle_exception()
routes it to self.object.need_restart so the stale worker set gets re-detected.
"""

from unittest import mock

import psutil
import pytest

from amplify.agent.collectors.nginx.metrics import NginxMetricsCollector


def _collector(processes):
    """Build a bare collector without running the heavy __init__ (mirrors test_runner_reinit)."""
    c = NginxMetricsCollector.__new__(NginxMetricsCollector)
    c.processes = processes
    c.zombies = set()
    c.previous_counters = {}  # abstract.py uses defaultdict(dict); plain dict is enough here
    c.object = mock.MagicMock()  # statsd.incr is a no-op MagicMock
    return c


def _proc(pid, read_bytes=None, write_bytes=None, io_side_effect=None):
    p = mock.MagicMock(pid=pid)
    if io_side_effect is not None:
        p.io_counters.side_effect = io_side_effect
    else:
        p.io_counters.return_value = mock.MagicMock(read_bytes=read_bytes, write_bytes=write_bytes)
    return p


def test_workers_io_skips_access_denied_and_sums_readable():
    """AccessDenied on one process is skipped; IO from the readable process is still summed."""
    good = _proc(100, read_bytes=2048, write_bytes=1024)
    denied = _proc(9309, io_side_effect=psutil.AccessDenied(9309))  # root-owned master

    c = _collector([good, denied])
    c.workers_io()  # must NOT raise

    # First call has no previous counter, so no incr() yet -- but the summed value is stored.
    assert c.previous_counters["nginx.workers.io.kbs_r"][1] == 2.0  # 2048 bytes / 1024
    assert c.previous_counters["nginx.workers.io.kbs_w"][1] == 1.0  # 1024 bytes / 1024


def test_workers_io_all_denied_does_not_raise():
    """Even if every process is inaccessible, the cycle completes (sums to zero)."""
    c = _collector([_proc(1, io_side_effect=psutil.AccessDenied(1))])
    c.workers_io()

    assert c.previous_counters["nginx.workers.io.kbs_r"][1] == 0
    assert c.previous_counters["nginx.workers.io.kbs_w"][1] == 0


def test_workers_io_propagates_no_such_process():
    """NoSuchProcess is NOT swallowed -- it must propagate so handle_exception sets need_restart."""
    c = _collector([_proc(100, io_side_effect=psutil.NoSuchProcess(100))])
    with pytest.raises(psutil.NoSuchProcess):
        c.workers_io()
