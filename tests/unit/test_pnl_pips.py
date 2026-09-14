"""pnl_pips existed in the model, the schema and the API — and was never written.

All 987 closed trades had it empty while the Examiner agent reasoned about
results and the order book showed a blank column. The broker reports the money
amount; pips have to be derived from the two prices.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from openforexai.data.normalizer import pnl_in_pips
from openforexai.models.trade import OrderStatus
from openforexai.repository_service import RepositoryService


# ── The calculation ──────────────────────────────────────────────────────────

def test_a_long_that_fell_shows_a_loss():
    assert pnl_in_pips("EURUSD", "BUY", Decimal("1.15607"), Decimal("1.15516")) == Decimal("-9.1")


def test_the_same_move_is_a_gain_for_a_short():
    """The sign is the whole point — abs() would report a loss as a win."""
    assert pnl_in_pips("EURUSD", "SELL", Decimal("1.15607"), Decimal("1.15516")) == Decimal("9.1")


def test_jpy_pairs_use_the_two_decimal_pip():
    assert pnl_in_pips("USDJPY", "BUY", Decimal("154.713"), Decimal("154.95")) == Decimal("23.7")


def test_a_missing_price_yields_nothing_rather_than_a_wrong_number():
    assert pnl_in_pips("EURUSD", "BUY", None, Decimal("1.1")) is None
    assert pnl_in_pips("EURUSD", "BUY", Decimal("1.1"), None) is None


def test_an_unknown_pair_falls_back_to_the_four_decimal_pip():
    assert pnl_in_pips("XAUUSD", "BUY", Decimal("1.0000"), Decimal("1.0010")) == Decimal("10.0")


# ── The wiring ───────────────────────────────────────────────────────────────

class _Entry:
    pair = "EURUSD"
    direction = "BUY"
    fill_price = Decimal("1.15607")
    close_price = None


class _Repo:
    def __init__(self, entry=None):
        self._entry = entry

    async def get_order_book_entry(self, entry_id):
        return self._entry


def _service(entry=None) -> RepositoryService:
    svc = RepositoryService.__new__(RepositoryService)
    svc._repository = _Repo(entry)
    return svc


@pytest.mark.asyncio
async def test_closing_an_entry_fills_in_the_pips():
    svc = _service(_Entry())
    args = await svc._with_pnl_pips({
        "entry_id": "x",
        "updates": {"status": OrderStatus.CLOSED.value, "close_price": "1.15516"},
    })
    assert args["updates"]["pnl_pips"] == "-9.1"


@pytest.mark.asyncio
async def test_an_update_that_does_not_close_is_left_alone():
    svc = _service(_Entry())
    args = await svc._with_pnl_pips({"entry_id": "x", "updates": {"status": "OPEN"}})
    assert "pnl_pips" not in args["updates"]


@pytest.mark.asyncio
async def test_a_value_supplied_by_the_caller_is_never_overwritten():
    svc = _service(_Entry())
    args = await svc._with_pnl_pips({
        "entry_id": "x",
        "updates": {"status": OrderStatus.CLOSED.value, "close_price": "1.15516", "pnl_pips": "42"},
    })
    assert args["updates"]["pnl_pips"] == "42"


@pytest.mark.asyncio
async def test_a_close_without_a_price_stays_empty():
    """Better a blank field than a number derived from nothing."""
    svc = _service(_Entry())
    args = await svc._with_pnl_pips({"entry_id": "x", "updates": {"status": OrderStatus.CLOSED.value}})
    assert "pnl_pips" not in args["updates"]


@pytest.mark.asyncio
async def test_a_vanished_entry_does_not_break_the_update():
    svc = _service(None)
    updates = {"status": OrderStatus.CLOSED.value, "close_price": "1.1"}
    args = await svc._with_pnl_pips({"entry_id": "x", "updates": updates})
    assert args["updates"] == updates
