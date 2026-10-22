import re

from amplify.agent.common.context import context
from amplify.agent.common.util import subp


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


VERSION_CMD = "%s --version"

# First line of `php-fpm --version`::
#   PHP 5.5.9-1ubuntu4.17 (fpm-fcgi) (built: May 19 2016 19:08:26)
# Anything else is not PHP. Agents up to 1.8.18 accepted any output, so a
# mis-resolved binary reported Python ("3.6.8") or systemd ("239") versions.
_PHP_LINE_RE = re.compile(r"^PHP (\d+\.\d+\.\d+)")


def VERSION_PARSER(bin_path):
    """
    :return: (version, raw_line) such as ('5.5.9', 'PHP 5.5.9-1ubuntu4.17 ...'),
             or (None, None) when the binary is not a PHP binary or fails.
    """
    try:
        raw_stdout, _ = subp.call(VERSION_CMD % bin_path)
    except Exception as e:
        exc_name = e.__class__.__name__
        # this is being logged as debug only since we will rely on bin_path
        # collection error to tip off support as to what is going wrong with
        # version detection
        context.log.debug(f'failed to get version info from "{bin_path}" due to {exc_name}')
        context.log.debug("additional info:", exc_info=True)
        return None, None

    raw_line = raw_stdout[0].strip() if raw_stdout else ""
    parsed = _PHP_LINE_RE.match(raw_line)
    if not parsed:
        context.log.debug(f'"{bin_path} --version" is not PHP: {raw_line!r}')
        return None, None
    return parsed.group(1), raw_line
