# -*- coding: utf-8 -*-
from __future__ import division  # Enable true division in Python 2
import time

from amplify.agent.common.context import context
from amplify.agent.collectors.abstract import AbstractMetricsCollector
from amplify.ext.varnish.util import get_varnishstat

__author__ = "GetPageSpeed"
__copyright__ = "Copyright (C) GetPageSpeed. All rights reserved."
__license__ = ""
__maintainer__ = "GetPageSpeed"
__email__ = "info@getpagespeed.com"


# Mapping of our metric names to varnishstat field names
METRICS = {
    "counters": {
        "varnish.cache.hit": "MAIN.cache_hit",
        "varnish.cache.miss": "MAIN.cache_miss",
        "varnish.cache.hitpass": "MAIN.cache_hitpass",
        "varnish.client.req": "MAIN.client_req",
        "varnish.client.conn": "MAIN.sess_conn",
        "varnish.backend.conn": "MAIN.backend_conn",
        "varnish.backend.req": "MAIN.backend_req",
        "varnish.backend.fail": "MAIN.backend_fail",
        "varnish.fetch.total": "MAIN.s_fetch",
        "varnish.threads.created": "MAIN.threads_created",
        "varnish.threads.failed": "MAIN.threads_failed",
    },
    "gauges": {
        "varnish.threads": "MAIN.threads",
        "varnish.threads.limited": "MAIN.threads_limited",
        "varnish.n_object": "MAIN.n_object",
        "varnish.n_objectcore": "MAIN.n_objectcore",
        "varnish.n_objecthead": "MAIN.n_objecthead",
        "varnish.n_backend": "MAIN.n_backend",
        "varnish.n_expired": "MAIN.n_expired",
        "varnish.n_lru_nuked": "MAIN.n_lru_nuked",
        "varnish.bans": "MAIN.bans",
    },
}


class VarnishMetricsCollector(AbstractMetricsCollector):
    """
    Metrics collector for Varnish. Collects cache statistics via varnishstat.
    """

    short_name = "varnish_metrics"
    status_metric_key = "varnish.status"

    def __init__(self, **kwargs):
        super(VarnishMetricsCollector, self).__init__(**kwargs)

        self.register(self.varnish_status)

    def varnish_status(self):
        """
        Collects data from varnishstat
        """
        stamp = int(time.time())

        # get varnishstat data
        stats = get_varnishstat()

        if not stats:
            context.log.debug("no varnishstat data collected")
            return

        # counters
        counted_vars = {}
        for metric, varnish_field in METRICS["counters"].items():
            if varnish_field in stats:
                counted_vars[metric] = stats[varnish_field]

        self.aggregate_counters(counted_vars, stamp=stamp)

        # gauges
        tracked_gauges = {}
        for metric, varnish_field in METRICS["gauges"].items():
            if varnish_field in stats:
                tracked_gauges[metric] = {
                    self.object.definition_hash: stats[varnish_field]
                }

        # Calculate cache hit ratio
        cache_hit = stats.get("MAIN.cache_hit", 0)
        cache_miss = stats.get("MAIN.cache_miss", 0)
        total_requests = cache_hit + cache_miss

        hit_ratio = 0.0
        if total_requests > 0:
            hit_ratio = (cache_hit / total_requests) * 100

        tracked_gauges["varnish.cache.hit_ratio"] = {
            self.object.definition_hash: hit_ratio
        }

        # Calculate backend hit ratio (successful backend connections)
        backend_conn = stats.get("MAIN.backend_conn", 0)
        backend_fail = stats.get("MAIN.backend_fail", 0)
        total_backend = backend_conn + backend_fail

        backend_success_ratio = 100.0
        if total_backend > 0:
            backend_success_ratio = (backend_conn / total_backend) * 100

        tracked_gauges["varnish.backend.success_ratio"] = {
            self.object.definition_hash: backend_success_ratio
        }

        self.aggregate_gauges(tracked_gauges, stamp=stamp)

        # finalize
        self.increment_counters()
        self.finalize_gauges()
