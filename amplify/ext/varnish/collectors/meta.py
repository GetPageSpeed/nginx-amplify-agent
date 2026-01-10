# -*- coding: utf-8 -*-
from amplify.agent.collectors.abstract import AbstractMetaCollector
from amplify.agent.common.context import context
from amplify.ext.varnish.util import version_parser

__author__ = "GetPageSpeed"
__copyright__ = "Copyright (C) GetPageSpeed. All rights reserved."
__license__ = ""
__maintainer__ = "GetPageSpeed"
__email__ = "info@getpagespeed.com"


class VarnishMetaCollector(AbstractMetaCollector):
    short_name = "varnish_meta"

    def __init__(self, **kwargs):
        super(VarnishMetaCollector, self).__init__(**kwargs)

        self._version = None
        self._version_line = None

        self.register(self.version)

    @property
    def default_meta(self):
        meta = {
            "type": self.object.type,
            "root_uuid": context.uuid,
            "local_id": self.object.local_id,
            "name": self.object.name,
            "display_name": self.object.display_name,
            "cmd": self.object.cmd,
            "conf_path": self.object.conf_path,
            "version": None,
            "can_have_children": False,
        }

        if not self.in_container:
            meta["pid"] = self.object.pid

        return meta

    def version(self):
        """
        Finds and sets version
        """
        if self._version is None:
            self._version, self._version_line = version_parser()

        self.meta["version"] = self._version
        self.object.version = self._version
