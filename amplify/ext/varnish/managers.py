# -*- coding: utf-8 -*-
import hashlib
import psutil

from amplify.agent.common.context import context
from amplify.agent.common.util import subp
from amplify.agent.managers.abstract import launch_method_supported
from amplify.agent.data.eventd import INFO
from amplify.ext.abstract.manager import ExtObjectManager
from amplify.ext.varnish.util import PS_CMD, ps_parser, master_parser
from amplify.ext.varnish import AMPLIFY_EXT_KEY
from amplify.ext.varnish.objects import VarnishObject


__author__ = "GetPageSpeed"
__copyright__ = "Copyright (C) GetPageSpeed. All rights reserved."
__license__ = ""
__maintainer__ = "GetPageSpeed"
__email__ = "info@getpagespeed.com"


class VarnishManager(ExtObjectManager):
    """
    Manager for Varnish objects.
    """

    ext = AMPLIFY_EXT_KEY

    name = "varnish_manager"
    type = "varnish"
    types = ("varnish",)

    def _discover_objects(self):
        # save the current ids
        existing_hashes = [
            obj.definition_hash for obj in self.objects.find_all(types=self.types)
        ]
        discovered_hashes = []

        varnish_daemons = self._find_all()

        while len(varnish_daemons):
            try:
                data = varnish_daemons.pop()

                definition = {
                    "type": "varnish",
                    "local_id": data["local_id"],
                    "root_uuid": context.uuid,
                }
                definition_hash = VarnishObject.hash(definition)
                discovered_hashes.append(definition_hash)

                if definition_hash not in existing_hashes:
                    # New object -- create it
                    new_obj = VarnishObject(data=data)

                    # Send discover event.
                    new_obj.eventd.event(
                        level=INFO,
                        message="varnishd process found, pid %s" % new_obj.pid,
                    )

                    self.objects.register(new_obj, parent_id=self.objects.root_id)

                elif definition_hash in existing_hashes:
                    for obj in self.objects.find_all(types=self.types):
                        if obj.definition_hash == definition_hash:
                            current_obj = obj
                            break

                    if current_obj.pid != data["pid"]:
                        # PIDs changed... Varnish must have been restarted
                        context.log.debug(
                            "varnishd was restarted (pid was %s now %s)"
                            % (current_obj.pid, data["pid"])
                        )
                        new_obj = VarnishObject(data=data)

                        # send Varnish restart event
                        new_obj.eventd.event(
                            level=INFO,
                            message="varnishd process was restarted, new pid %s, old pid %s"
                            % (new_obj.pid, current_obj.pid),
                        )

                        # stop and un-register children
                        children_objects = self.objects.find_all(
                            obj_id=current_obj.id, children=True, include_self=False
                        )

                        for child_obj in children_objects:
                            child_obj.stop()
                            self.objects.unregister(obj=child_obj)

                        # un-register old object
                        self.objects.unregister(current_obj)

                        # stop old object
                        current_obj.stop()

                        self.objects.register(new_obj, parent_id=self.objects.root_id)
            except psutil.NoSuchProcess:
                context.log.debug(
                    "varnishd is restarting/reloading, pids are changing, agent is waiting"
                )

        # check if we left something in objects (Varnish could be stopped or something)
        dropped_hashes = list(
            filter(lambda x: x not in discovered_hashes, existing_hashes)
        )

        if len(dropped_hashes) == 0:
            return

        for dropped_hash in dropped_hashes:
            for obj in self.objects.find_all(types=self.types):
                if obj.definition_hash == dropped_hash:
                    dropped_obj = obj
                    break

        context.log.debug("varnishd was stopped (pid was %s)" % dropped_obj.pid)

        # stop and un-register children
        children_objects = self.objects.find_all(
            obj_id=dropped_obj.id, children=True, include_self=False
        )

        for child_obj in children_objects:
            child_obj.stop()
            self.objects.unregister(child_obj)

        dropped_obj.stop()
        self.objects.unregister(dropped_obj)

    @staticmethod
    def _find_all(ps=None):
        """
        Tries to find all varnishd processes

        :param ps: [] of str, used for debugging our parsing logic - should be None most of the time
        :return: [] of {} Varnish object definitions
        """
        # get ps info
        try:
            # set ps output to passed param or call subp
            ps, _ = (ps, None) if ps is not None else subp.call(PS_CMD)
            context.log.debug("ps varnishd output: %s" % ps)
        except Exception as e:
            # log error
            exception_name = e.__class__.__name__
            context.log.debug(
                'failed to find running varnishd via "%s" due to %s'
                % (PS_CMD, exception_name)
            )
            context.log.debug("additional info:", exc_info=True)

            # If there is a root_object defined, log an event to send to the cloud.
            if context.objects.root_object:
                context.objects.root_object.eventd.event(
                    level=INFO, message="no varnishd processes found"
                )

            # break processing returning a fault-tolerant empty list
            return []

        if not any("varnishd" in line for line in ps):
            context.log.info("no varnishd processes found")

            # break processing returning a fault-tolerant empty list
            return []

        # collect all info about processes
        masters = {}
        try:
            for line in ps:
                parsed = ps_parser(line)

                # if not parsed - go to the next line
                if parsed is None:
                    continue

                pid, ppid, cmd = parsed  # unpack values

                # match master/main process (varnishd command)
                if "varnishd" in cmd:
                    if not launch_method_supported("varnish", ppid):
                        continue

                    try:
                        conf_path = master_parser(cmd)
                    except Exception:
                        context.log.error("failed to find conf_path for %s" % cmd)
                        context.log.debug("additional info:", exc_info=True)
                    else:
                        # calculate local_id
                        local_string_id = "%s_%s" % (cmd, conf_path)
                        local_id = hashlib.sha256(
                            local_string_id.encode("utf-8")
                        ).hexdigest()

                        if pid not in masters:
                            masters[pid] = {}

                        masters[pid].update(
                            {
                                "cmd": cmd.strip(),
                                "conf_path": conf_path,
                                "pid": pid,
                                "local_id": local_id,
                            }
                        )
        except Exception as e:
            # log error
            exception_name = e.__class__.__name__
            context.log.error("failed to parse ps results due to %s" % exception_name)
            context.log.debug("additional info:", exc_info=True)

        # format results
        results = []
        for payload in masters.values():
            # only add payloads that have all the keys
            if (
                "cmd" in payload
                and "conf_path" in payload
                and "pid" in payload
                and "local_id" in payload
            ):
                results.append(payload)
            else:
                context.log.debug(
                    'Varnish "_find_all()" found an incomplete entity %s' % payload
                )

        return results
