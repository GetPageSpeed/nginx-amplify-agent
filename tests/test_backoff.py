"""
Regression test for exponential_delay TypeError on Python 3.12+.

period_size is a float (the exponential formula starts with
1.0/EXPONENTIAL_COEFFICIENT). randint() became strict about int args
in Python 3.12; the unfixed code raised TypeError on every backoff
attempt on Noble/Trixie/EL10/Fedora/SLES16.

See https://github.com/nginxinc/nginx-amplify-agent/pull/125
"""
import pytest

from amplify.agent.common.util.backoff import exponential_delay


@pytest.mark.parametrize("n", [0, 1, 2, 5, 10, 20, 50])
def test_exponential_delay_returns_int(n):
    result = exponential_delay(n)
    assert isinstance(result, int)
    assert result >= 0


def test_exponential_delay_capped_at_maximum_timeout():
    result = exponential_delay(100)
    assert isinstance(result, int)
    assert 0 <= result < 3600
