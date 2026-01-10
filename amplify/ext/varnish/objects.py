# -*- coding: utf-8 -*-
from amplify.agent.common.util.host import hostname
from amplify.ext.abstract.object import AbstractExtObject
from amplify.ext.varnish.collectors.meta import VarnishMetaCollector
from amplify.ext.varnish.collectors.metrics import VarnishMetricsCollector

__author__ = "GetPageSpeed"
__copyright__ = "Copyright (C) GetPageSpeed. All rights reserved."
__license__ = ""
__maintainer__ = "GetPageSpeed"
__email__ = "info@getpagespeed.com"


class VarnishObject(AbstractExtObject):
    type = "varnish"

    def __init__(self, **kwargs):
        super(VarnishObject, self).__init__(**kwargs)

        self.name = "varnish"

        # cached values
        self._local_id = self.data.get("local_id", None)

        # attributes
        self.pid = self.data["pid"]
        self.cmd = self.data["cmd"]
        self.conf_path = self.data["conf_path"]

        # state
        self.version = None

        # collectors
        self._setup_meta_collector()
        self._setup_metrics_collector()

    @property
    def display_name(self):
        return "varnish @ %s" % hostname()

    @property
    def local_id_args(self):
        return self.cmd, self.conf_path

    def _setup_meta_collector(self):
        self.collectors.append(
            VarnishMetaCollector(object=self, interval=self.intervals["meta"])
        )

    def _setup_metrics_collector(self):
        self.collectors.append(
            VarnishMetricsCollector(object=self, interval=self.intervals["metrics"])
        )
