"""A refusal the guard is designed to make is a result, not an error.

The price guard refuses a note after almost every closed trade — the examiner
names a level, the guard says "in pips, not in prices". That is the guard
working. Reported as an error with a stack trace, arriving in the console
right behind the trade notification, it teaches whoever watches to stop
reading errors at all, and then the one that matters goes unread too.

It also used to destroy the observation. Now the reason travels back to the
caller, which is what the examiner needs to rewrite the note instead of
losing it.
"""
from __future__ import annotations

import pytest

from openforexai.services.semantic_memory_service import (
    MemoryRejected,
    _reject_absolute_price_quotes,
    find_absolute_price_quotes,
)


def test_an_absolute_price_is_refused_with_its_own_class() -> None:
    with pytest.raises(MemoryRejected):
        _reject_absolute_price_quotes("Stop lag bei 155.929 unter dem Einstieg", "USDJPY")


def test_the_refusal_says_how_to_fix_it() -> None:
    """The message is read by the examiner, so it has to be actionable."""
    with pytest.raises(MemoryRejected) as exc:
        _reject_absolute_price_quotes("stop at 158.946", "USDJPY")
    text = str(exc.value)
    assert "pips" in text
    assert "158.946" in text, "name the offending value, not just the rule"


def test_relative_wording_passes() -> None:
    _reject_absolute_price_quotes("Stop about 6 pips below the entry", "USDJPY")
    _reject_absolute_price_quotes("price in the upper third of the range", "EURUSD")


def test_it_is_distinguishable_from_a_real_failure() -> None:
    """The whole point: the service must be able to tell them apart."""
    assert issubclass(MemoryRejected, ValueError)
    assert not isinstance(RuntimeError("disk on fire"), MemoryRejected)


@pytest.mark.parametrize(("text", "pair", "expected"), [
    ("EURUSD at 1,14623 on the retest", "EURUSD", True),
    ("USDJPY reached 156.263", "USDJPY", True),
    ("moved 15.5 pips against the entry", "USDJPY", False),
    ("about 2.3 ATR from the level", "USDJPY", False),
])
def test_the_heuristic_on_the_values_seen_in_production(
    text: str, pair: str, expected: bool,
) -> None:
    """The four shapes the guard actually met in the logs."""
    assert bool(find_absolute_price_quotes(text, pair)) is expected


@pytest.mark.asyncio
async def test_the_service_answers_with_a_result_not_an_error() -> None:
    """A refusal must not reach the caller as a raised exception, or the
    observation is lost and the console gets an error it cannot act on."""
    from openforexai.services import semantic_memory_service as svc

    class _Bus:
        def __init__(self) -> None:
            self.sent: list = []

        async def publish(self, message, triggered_by=None):
            self.sent.append(message)

    service = svc.SemanticMemoryService.__new__(svc.SemanticMemoryService)
    service._bus = _Bus()

    async def _refuse(args):
        _reject_absolute_price_quotes("stop at 155.929", "USDJPY")

    service.remember = _refuse

    from openforexai.models.messaging import AgentMessage, EventType
    msg = AgentMessage(
        event_type=EventType.MEMORY_REQUEST, source_agent_id="EA",
        payload={"operation": "remember", "args": {}},
    )
    await svc.SemanticMemoryService._handle(service, msg)

    payload = service._bus.sent[0].payload
    assert payload["error"] is None, "a designed refusal is not an error"
    assert payload["result"]["status"] == "rejected"
    assert payload["result"]["stored"] is False
    assert "pips" in payload["result"]["reason"], "the caller needs to know how to fix it"
