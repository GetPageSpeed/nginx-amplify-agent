import configparser
import logging
import logging.config
import logging.handlers

from amplify.agent.common.context import context

try:
    import thread
except ImportError:
    # Renamed in Python 3
    import _thread as thread


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"

LOGGERS_CACHE = {}

DEFAULT_LOG_FILE = "/var/log/amplify-agent/agent.log"
DEFAULT_LOG_FORMAT = "%(asctime)s [%(process)d] %(threadName)s %(message)s"


class NAASLogRecord(logging.LogRecord):
    def __init__(self, *args, **kwargs):
        logging.LogRecord.__init__(self, *args, **kwargs)
        thread_id = thread.get_ident()
        self.action_id = context.action_ids.get(thread_id, 0)


class NAASLogger(logging.getLoggerClass()):
    @staticmethod
    def makeRecord(name, level, fn, lno, msg, args, exc_info, func=None, extra=None, sinfo=None):
        return NAASLogRecord(name, level, fn, lno, msg, args, exc_info, func)


logging.setLoggerClass(NAASLogger)


def setup(logger_file, agent_log_file=DEFAULT_LOG_FILE):
    try:
        logging.config.fileConfig(logger_file)
    except (KeyError, RuntimeError, configparser.Error):
        # agent.conf is missing the optional Python logging INI sections
        # ([loggers]/[handlers]/[formatters]). Fall back to programmatic
        # defaults so the agent still starts; log a single WARNING so
        # support can grep journal for this state.
        _apply_default_logging(agent_log_file)
        logging.getLogger("agent-default").warning(
            "agent.conf is missing [loggers]/[handlers]/[formatters] sections; "
            "using built-in defaults. Compare with /etc/amplify-agent/agent.conf.default "
            "to restore custom logging."
        )


def _apply_default_logging(agent_log_file):
    """Programmatic equivalent of agent.conf.default lines 44-94."""
    formatter = logging.Formatter(DEFAULT_LOG_FORMAT)

    devnull_handler = logging.handlers.WatchedFileHandler("/dev/null")
    devnull_handler.setLevel(logging.DEBUG)
    devnull_handler.setFormatter(formatter)

    root_handler = logging.handlers.WatchedFileHandler("/dev/null")
    root_handler.setLevel(logging.DEBUG)
    root_handler.setFormatter(formatter)

    agent_handler = logging.handlers.WatchedFileHandler(agent_log_file, "a", None, True)
    agent_handler.setLevel(logging.INFO)
    agent_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [root_handler]
    root_logger.setLevel(logging.DEBUG)

    devnull_logger = logging.getLogger("devnull")
    devnull_logger.handlers = [devnull_handler]
    devnull_logger.setLevel(logging.DEBUG)
    devnull_logger.propagate = False

    agent_logger = logging.getLogger("agent-default")
    agent_logger.handlers = [agent_handler]
    agent_logger.setLevel(logging.INFO)
    agent_logger.propagate = False


def get(log_name):
    """
    Creates logger object to specified log and caches it in LOGGERS_CACHE dict

    :param log_name: log name
    :return: logger object
    """
    if log_name not in LOGGERS_CACHE:
        logger = logging.getLogger(log_name)
        LOGGERS_CACHE[log_name] = logger
    return LOGGERS_CACHE[log_name]


def get_debug_handler(log_file):
    """
    returns a file handler for debug log file
    :param log_file: str log file
    :return: FileHandler obj
    """
    handler = logging.FileHandler(log_file, "a")
    formatter = logging.Formatter("%(asctime)s [%(process)d] %(action_id)s %(threadName)s %(message)s")
    handler.setFormatter(formatter)
    return handler
