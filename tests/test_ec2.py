"""Tests for Amazon EC2 instance identity metadata collection."""

from amplify.agent.common.util.ec2 import AmazonEC2


class FakeHTTPClient:
    """Return configured IMDS values and fail all other metadata reads."""

    def __init__(self, values):
        self.values = values

    def get(self, url, **kwargs):
        field = url.rsplit("/latest/meta-data/", 1)[1]
        value = self.values.get(field)
        if isinstance(value, Exception):
            raise value
        return value


def _read(monkeypatch, values):
    monkeypatch.setattr(AmazonEC2, "metadata", {})
    monkeypatch.setattr(
        "amplify.agent.common.util.ec2.context.http_client",
        FakeHTTPClient(values),
    )
    return AmazonEC2.read_meta()


def test_read_meta_emits_ec2_instance_identity(monkeypatch):
    metadata = _read(
        monkeypatch,
        {
            "instance-id": "i-0123456789abcdef0",
            "placement/region": "ap-southeast-1",
            "placement/availability-zone": "ap-southeast-1b",
        },
    )

    assert metadata["instance-id"] == "i-0123456789abcdef0"
    assert metadata["placement/region"] == "ap-southeast-1"
    assert metadata["placement/availability-zone"] == "ap-southeast-1b"


def test_read_meta_keeps_available_identity_fields_on_partial_failure(monkeypatch):
    metadata = _read(
        monkeypatch,
        {
            "instance-id": "i-0123456789abcdef0",
            "placement/region": RuntimeError("IMDS unavailable"),
            "placement/availability-zone": "ap-southeast-1b",
        },
    )

    assert metadata["instance-id"] == "i-0123456789abcdef0"
    assert "placement/region" not in metadata
    assert metadata["placement/availability-zone"] == "ap-southeast-1b"


def test_read_meta_returns_empty_mapping_outside_ec2(monkeypatch):
    assert _read(monkeypatch, {}) == {}
