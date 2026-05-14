"""
Tests for amplify.agent.common.util.logger.setup().

The agent's logging is loaded from agent.conf via logging.config.fileConfig().
A customer-supplied agent.conf may omit the optional [loggers]/[handlers]/
[formatters] sections (e.g. when produced by an older migrate.sh or
hand-written from upstream NGINX Amplify docs). In that case setup() must
fall back to built-in defaults instead of crashing the agent at startup.
"""

import logging
import textwrap

import pytest

from amplify.agent.common.util import logger as agent_logger


FULL_INI = textwrap.dedent(
    """
    [credentials]
    api_key = test-key

    [cloud]
    api_url = https://amplify.getpagespeed.com/1.4

    [loggers]
    keys = root,devnull,agent-default

    [handlers]
    keys = root,devnull,agent-default

    [formatters]
    keys = simpleFormatter

    [formatter_simpleFormatter]
    format = %(asctime)s [%(process)d] %(threadName)s %(message)s
    datefmt =

    [logger_root]
    level = DEBUG
    handlers = root
    qualname = root
    formatter = simpleFormatter
    propagate = 0

    [logger_devnull]
    level = DEBUG
    qualname = devnull
    handlers = devnull
    formatter = simpleFormatter
    propagate = 0

    [logger_agent-default]
    level = INFO
    qualname = agent-default
    handlers = agent-default
    formatter = simpleFormatter
    propagate = 0

    [handler_root]
    class = logging.handlers.WatchedFileHandler
    level = DEBUG
    formatter = simpleFormatter
    args = ('{root_log}',)

    [handler_devnull]
    class = logging.handlers.WatchedFileHandler
    level = DEBUG
    formatter = simpleFormatter
    args = ('{devnull_log}',)

    [handler_agent-default]
    class = logging.handlers.WatchedFileHandler
    level = INFO
    formatter = simpleFormatter
    args = ('{agent_log}', 'a', None, 1)
"""
).strip()


MINIMAL_INI = textwrap.dedent(
    """
    [credentials]
    api_key = test-key

    [cloud]
    api_url = https://amplify.getpagespeed.com/1.4
"""
).strip()


@pytest.fixture(autouse=True)
def _reset_logging():
    """Reset root logger handlers between tests so cases don't bleed into each other."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    yield
    for logger_name in ("agent-default", "devnull"):
        lg = logging.getLogger(logger_name)
        for h in lg.handlers[:]:
            lg.removeHandler(h)
            h.close()
    for h in root.handlers[:]:
        root.removeHandler(h)
        h.close()
    for h in saved_handlers:
        root.addHandler(h)
    root.setLevel(saved_level)


def test_setup_with_full_config(tmp_path):
    """fileConfig path: full agent.conf produces a working agent-default logger."""
    agent_log = tmp_path / "agent.log"
    root_log = tmp_path / "root.log"
    devnull_log = tmp_path / "devnull.log"
    conf = tmp_path / "agent.conf"
    conf.write_text(
        FULL_INI.format(
            agent_log=str(agent_log),
            root_log=str(root_log),
            devnull_log=str(devnull_log),
        )
    )

    agent_logger.setup(str(conf))

    logging.getLogger("agent-default").info("hello full")
    for h in logging.getLogger("agent-default").handlers:
        h.flush()
    assert "hello full" in agent_log.read_text()


def test_setup_with_minimal_config_falls_back(tmp_path):
    """Minimal agent.conf (only [credentials]+[cloud]) must not crash setup()."""
    agent_log = tmp_path / "agent.log"
    conf = tmp_path / "agent.conf"
    conf.write_text(MINIMAL_INI)

    # Should not raise.
    agent_logger.setup(str(conf), agent_log_file=str(agent_log))

    agent_default = logging.getLogger("agent-default")
    assert agent_default.handlers, "agent-default logger should have a handler after fallback"

    agent_default.info("hello minimal")
    for h in agent_default.handlers:
        h.flush()
    assert agent_log.exists(), "agent log file should be created by fallback handler"
    assert "hello minimal" in agent_log.read_text()


def test_setup_with_empty_file_falls_back(tmp_path):
    """Edge case: empty agent.conf also triggers fallback rather than crashing."""
    agent_log = tmp_path / "agent.log"
    conf = tmp_path / "agent.conf"
    conf.write_text("")

    agent_logger.setup(str(conf), agent_log_file=str(agent_log))

    assert logging.getLogger("agent-default").handlers
