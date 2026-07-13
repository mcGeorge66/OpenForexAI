from __future__ import annotations

import asyncio
from unittest.mock import Mock

import pytest

from openforexai.adapters.brokers.mt5 import MT5Broker


class _BlockingCallable:
    def __init__(self, *, delay_seconds: float, result):
        self.delay_seconds = delay_seconds
        self.result = result

    def __call__(self):
        import time

        time.sleep(self.delay_seconds)
        return self.result


@pytest.mark.parametrize("delay_seconds,timeout_seconds,should_timeout", [
    (0.01, 0.2, False),
    (0.2, 0.05, True),
])
async def test_mt5_call_blocking_uses_timeout(
    delay_seconds: float,
    timeout_seconds: float,
    should_timeout: bool,
) -> None:
    broker = object.__new__(MT5Broker)
    broker._short_name = "OXS_T"
    broker._api_timeout_seconds = timeout_seconds
    broker._mt5 = Mock()

    if should_timeout:
        with pytest.raises(TimeoutError):
            await broker._call_blocking("test_call", _BlockingCallable(delay_seconds=delay_seconds, result=123))
    else:
        result = await broker._call_blocking(
            "test_call",
            _BlockingCallable(delay_seconds=delay_seconds, result=123),
        )
        assert result == 123
