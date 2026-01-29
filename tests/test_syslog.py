"""
Tests for the syslog pipeline module.
"""


def test_syslog_module_imports():
    """Test that syslog module can be imported."""
    from amplify.agent.pipelines import syslog

    assert syslog is not None


def test_syslog_tail_class_exists():
    """Test that SyslogTail class is available."""
    from amplify.agent.pipelines.syslog import SyslogTail

    assert SyslogTail is not None


def test_syslog_server_class_exists():
    """Test that SyslogServer class is available."""
    from amplify.agent.pipelines.syslog import SyslogServer

    assert SyslogServer is not None


def test_syslog_listener_class_exists():
    """Test that SyslogListener class is available."""
    from amplify.agent.pipelines.syslog import SyslogListener

    assert SyslogListener is not None
