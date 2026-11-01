"""amzn2 must pin its requests dependency to the Python 3.7 package.

Regression: on Amazon Linux 2 with EPEL enabled, yum satisfied a plain
`Requires: python3-requests` with EPEL 7's python36-requests. That package needs
python(abi) = 3.6, which amzn2 does not have, so the agent would not install
(repotest epel-independence-gate). Only amzn2's own package owns this path.
"""
import re
from pathlib import Path

SPEC = Path(__file__).resolve().parents[1] / "packages/nginx-amplify-agent/rpm/nginx-amplify-agent.spec"
PINNED = "Requires: /usr/lib/python3.7/site-packages/requests/__init__.py"


def test_amzn2_requires_requests_by_path():
    block = re.search(r"%if 0%\{\?amzn\} == 2\n(.*?)%else\n(.*?)%endif", SPEC.read_text(), re.S)
    assert block, "amzn2-only Requires block is missing"
    amzn2, other = block.groups()
    assert PINNED in amzn2
    assert "Requires: python3-requests" not in amzn2
    assert "Requires: python3-requests" in other


def test_el7_requires_block_skips_amzn2():
    """amzn2 also defines rhel 7, so an EL7-only block must exclude it."""
    assert "%if 0%{?rhel} == 7 && 0%{?amzn} == 0\n" in SPEC.read_text()
    assert "%if 0%{?rhel} == 7\n" not in SPEC.read_text()
