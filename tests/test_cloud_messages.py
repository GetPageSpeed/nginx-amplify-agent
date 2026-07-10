"""
Tests for the CloudResponse.messages admin-broadcast pipeline.

Background: the Amplify server (GPS fork) shipped an admin broadcast feature
on 2026-06-15 -- POST /1.4/{api_key}/agent/ now returns a `messages: []` array
so admins can push notices to every agent. amplify.agent.common.cloud.CloudResponse
already parsed the field, but amplify.agent.supervisor.talk_to_cloud() silently
dropped it (only objects/versions/capabilities/config were processed). This
pins the fix: every non-empty string in cloud_response.messages must reach the
agent log via supervisor.log_cloud_messages().
"""

import logging

from amplify.agent.common.cloud import CloudResponse
from amplify.agent.supervisor import log_cloud_messages


def _response(messages=None):
    payload = {"versions": {"current": "1.8.16", "obsolete": "1.0.0", "old": "1.5.0"}}
    if messages is not None:
        payload["messages"] = messages
    return payload


def test_cloud_response_parses_messages():
    response = CloudResponse(_response(["hi", "second"]))
    assert response.messages == ["hi", "second"]


def test_cloud_response_defaults_missing_messages_to_empty_list():
    response = CloudResponse(_response())
    assert response.messages == []


def test_cloud_response_preserves_empty_messages_list():
    response = CloudResponse(_response([]))
    assert response.messages == []


def test_log_cloud_messages_logs_every_message(caplog):
    log = logging.getLogger("test-cloud-messages-happy")
    with caplog.at_level(logging.INFO, logger=log.name):
        log_cloud_messages(["hi", "second"], log)

    records = [r.getMessage() for r in caplog.records if r.name == log.name]
    assert records == ["amplify message: hi", "amplify message: second"]


def test_log_cloud_messages_empty_list_logs_nothing(caplog):
    log = logging.getLogger("test-cloud-messages-empty")
    with caplog.at_level(logging.INFO, logger=log.name):
        log_cloud_messages([], log)

    assert [r for r in caplog.records if r.name == log.name] == []


def test_log_cloud_messages_skips_falsey_entries(caplog):
    log = logging.getLogger("test-cloud-messages-falsey")
    with caplog.at_level(logging.INFO, logger=log.name):
        log_cloud_messages(["", None], log)

    assert [r for r in caplog.records if r.name == log.name] == []
