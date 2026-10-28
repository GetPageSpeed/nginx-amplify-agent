"""The repo's own tests/ must never ship as a top-level site-packages package.

Regression: the EL7 RPM installed site-packages/tests/__init__.py, which EPEL's
python36-suds also owns, so hosts with both aborted yum at the rpm
file-conflict test (repotest coinstall gate).
"""
import os
import sys
from unittest import mock

import pytest
import setuptools

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.parametrize("setup_file", ["packages/nginx-amplify-agent/setup-rpm.py"])
def test_tests_package_not_shipped(setup_file, monkeypatch):
    captured = {}
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(sys, "argv", ["setup.py", "--version"])
    with mock.patch.object(setuptools, "setup", side_effect=lambda **kw: captured.update(kw)):
        with open(os.path.join(ROOT, setup_file)) as fh:
            code = compile(fh.read(), setup_file, "exec")
        exec(code, {"__name__": "__main__", "__file__": os.path.join(ROOT, setup_file)})
    packages = captured["packages"]
    assert "amplify" in packages
    leaked = [p for p in packages if p.split(".")[0] in ("tests", "test", "tools", "packages")]
    assert leaked == []
