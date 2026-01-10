# -*- coding: utf-8 -*-
import re

from amplify.agent.common.context import context
from amplify.agent.common.util import subp


__author__ = "GetPageSpeed"
__copyright__ = "Copyright (C) GetPageSpeed. All rights reserved."
__license__ = ""
__maintainer__ = "GetPageSpeed"
__email__ = "info@getpagespeed.com"


PS_CMD = "ps xao pid,ppid,command | grep '[v]arnishd'"
PS_REGEX = re.compile(r"\s*(?P<pid>\d+)\s+(?P<ppid>\d+)\s+(?P<cmd>.+)\s*")

VARNISHSTAT_CMD = "varnishstat -1"
# Parse lines like: MAIN.cache_hit              12345         0.00 Cache hits
VARNISHSTAT_REGEX = re.compile(r"^(?P<name>\S+)\s+(?P<value>\d+)\s+")

VERSION_CMD = "varnishd -V"


def ps_parser(ps_line):
    """
    Parses PS response line, for example:
    26753     1 /usr/sbin/varnishd -P /run/varnish.pid -a :6081 -f /etc/varnish/default.vcl

    :param ps_line: str ps line
    :return: (int pid, int ppid, str cmd) or None
    """
    parsed = PS_REGEX.match(ps_line)

    if not parsed:
        return None

    pid, ppid, cmd = (
        int(parsed.group("pid")),
        int(parsed.group("ppid")),
        parsed.group("cmd"),
    )
    return pid, ppid, cmd


def varnishstat_parser(output_lines):
    """
    Parses varnishstat -1 output and returns a dict of metric_name -> value

    Example output line:
    MAIN.cache_hit              12345         0.00 Cache hits

    :param output_lines: list of str lines from varnishstat -1
    :return: dict metric_name -> int value
    """
    result = {}
    for line in output_lines:
        parsed = VARNISHSTAT_REGEX.match(line)
        if parsed:
            result[parsed.group("name")] = int(parsed.group("value"))
    return result


def get_varnishstat():
    """
    Runs varnishstat -1 and returns parsed metrics

    :return: dict metric_name -> int value
    """
    try:
        stdout, _ = subp.call(VARNISHSTAT_CMD)
        return varnishstat_parser(stdout)
    except Exception as e:
        exception_name = e.__class__.__name__
        context.log.debug("failed to run varnishstat due to %s" % exception_name)
        context.log.debug("additional info:", exc_info=True)
        return {}


def version_parser():
    """
    Runs varnishd -V and parses version

    :return: tuple (version_string, full_output) or (None, None)
    """
    try:
        # varnishd -V outputs to stderr
        stdout, stderr = subp.call(VERSION_CMD, check=False)
        # Combine stdout and stderr
        output = stdout + stderr
        if output:
            raw_line = output[0]
            # Parse: varnishd (varnish-6.0.7 revision 123abc)
            match = re.search(
                r"varnish[d]?\s*[\(\-]?\s*[vV]?(?:arnish-)?(\d+\.\d+\.?\d*)", raw_line
            )
            if match:
                return match.group(1), raw_line
    except Exception as e:
        exception_name = e.__class__.__name__
        context.log.debug("failed to get varnish version due to %s" % exception_name)
        context.log.debug("additional info:", exc_info=True)

    return None, None


def master_parser(ps_master_cmd):
    """
    Parses the master command to extract config path

    :param ps_master_cmd: str master cmd line
    :return: str path to config file or default
    """
    # Look for -f /path/to/config.vcl
    match = re.search(r"-f\s+(\S+)", ps_master_cmd)
    if match:
        return match.group(1)

    # Default VCL location
    return "/etc/varnish/default.vcl"
