"""The time anchor must be impossible to forget.

Every tool that reads candles goes through ``base.fetch_candles()``, which
always sends ``context.as_of``. Before this, the anchor was forced into the
arguments of three tools *by name* — and the three newest candle-reading tools
were not on that list (``compute_fomak`` spells its parameter ``anchor``,
``compute_fopok`` and ``detect_impulse_pullback`` have none). They read live
candles while the simulator showed a position weeks in the past, silently.

The structural test below is the one that matters: a new tool that builds its
own CANDLES_REQUEST reopens exactly that hole, so no tool may.
"""
from __future__ import annotations

import pathlib

import pytest

from openforexai.tools.base import ToolContext, fetch_candles

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "openforexai" / "tools"


def test_no_tool_builds_its_own_candles_request() -> None:
    """base.py is the only place allowed to ask for candles."""
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted(TOOLS_DIR.rglob("*.py"))
        if path.name != "base.py" and "CANDLES_REQUEST" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], (
        "These tools request candles themselves and therefore bypass the time "
        "anchor — route them through base.fetch_candles() instead: "
        + ", ".join(offenders)
    )


class _RecordingBus:
    """Captures the payload instead of talking to a DataContainer."""

    def __init__(self, candles: list[dict] | None = None) -> None:
        self.payloads: list[dict] = []
        self._candles = candles if candles is not None else [{"close": "1.0"}]

    def register_response_future(self, key, future):
        self._future = future

    def cancel_response_future(self, key):
        pass

    async def publish(self, message, triggered_by=None):
        self.payloads.append(dict(message.payload))
        self._future.set_result({"candles": list(self._candles)})


def _context(bus: _RecordingBus, as_of: str | None) -> ToolContext:
    return ToolContext(
        agent_id="TEST_-ALL___-GA-TEST",
        broker_name="OXS_T",
        pair="USDJPY",
        event_bus=bus,
        as_of=as_of,
    )


@pytest.mark.asyncio
async def test_as_of_is_sent_as_start() -> None:
    bus = _RecordingBus()
    await fetch_candles(_context(bus, "2026-07-01T12:00:00+00:00"), "M5", 10)
    assert bus.payloads[0]["start"] == "2026-07-01T12:00:00+00:00"
    assert bus.payloads[0]["timeframe"] == "M5"
    assert bus.payloads[0]["limit"] == 10


@pytest.mark.asyncio
async def test_live_context_sends_no_anchor() -> None:
    """Without an anchor the request must stay exactly as it was before."""
    bus = _RecordingBus()
    await fetch_candles(_context(bus, None), "M5", 10)
    assert "start" not in bus.payloads[0]


@pytest.mark.asyncio
async def test_context_anchor_wins_over_argument() -> None:
    """Fail-closed: inside a simulation a tool argument cannot widen the window.

    Otherwise a prompt could ask for live data while the user looks at a frozen
    position — the same class of silent divergence the anchor exists to prevent.
    """
    bus = _RecordingBus()
    await fetch_candles(
        _context(bus, "2026-07-01T12:00:00+00:00"), "M5", 10,
        start="2026-09-16T00:00:00+00:00",
    )
    assert bus.payloads[0]["start"] == "2026-07-01T12:00:00+00:00"


@pytest.mark.asyncio
async def test_argument_still_works_without_context_anchor() -> None:
    """Live: an explicit `start` remains the documented way to look back."""
    bus = _RecordingBus()
    await fetch_candles(
        _context(bus, None), "M5", 10, start="2026-09-16T00:00:00+00:00",
    )
    assert bus.payloads[0]["start"] == "2026-09-16T00:00:00+00:00"


@pytest.mark.asyncio
async def test_error_response_raises() -> None:
    class _ErrorBus(_RecordingBus):
        async def publish(self, message, triggered_by=None):
            self.payloads.append(dict(message.payload))
            self._future.set_result({"error": "no data"})

    bus = _ErrorBus()
    with pytest.raises(RuntimeError, match="no data"):
        await fetch_candles(_context(bus, None), "M5", 10)


@pytest.mark.asyncio
async def test_returns_only_the_last_count_candles() -> None:
    bus = _RecordingBus(candles=[{"close": str(i)} for i in range(50)])
    result = await fetch_candles(_context(bus, None), "M5", 3)
    assert [c["close"] for c in result] == ["47", "48", "49"]


@pytest.mark.asyncio
async def test_pair_override_reaches_the_request() -> None:
    """DXY components and the FOMAK higher timeframe read other pairs."""
    bus = _RecordingBus()
    await fetch_candles(_context(bus, None), "H1", 5, pair="EURUSD")
    # The pair travels as the message instrument, not in the payload.
    assert bus.payloads[0]["timeframe"] == "H1"


# ── The three tools that used to ignore the anchor ─────────────────────────

_ANCHOR = "2026-07-01T12:00:00+00:00"


def _synthetic_candles(count: int) -> list[dict]:
    """Rising candles — enough shape for the tools to do arithmetic on."""
    from datetime import UTC, datetime, timedelta

    base = datetime(2026, 6, 1, tzinfo=UTC)
    out = []
    for i in range(count):
        price = 150.0 + i * 0.01
        out.append({
            "timestamp": (base + timedelta(minutes=5 * i)).isoformat(),
            "open": str(price), "high": str(price + 0.02),
            "low": str(price - 0.02), "close": str(price),
            "tick_volume": 100, "spread": "1.1", "timeframe": "M5",
        })
    return out


@pytest.fixture
def recorded_requests(monkeypatch):
    """Every candle request the tool makes, recorded at base.bus_request."""
    calls: list[dict] = []

    async def _fake(context, event_type, target_id, payload, instrument=None, timeout=30.0):
        calls.append({"payload": dict(payload), "instrument": instrument})
        return {"candles": _synthetic_candles(int(payload["limit"])), "error": None}

    monkeypatch.setattr("openforexai.tools.base.bus_request", _fake)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "class_name", "arguments"),
    [
        # Spells its anchor argument `anchor`, so the old per-name forcing of
        # `start` never reached it.
        ("compute_fomak", "ComputeFomakTool", {"timeframe": "M5", "lookback_candles": 24}),
        # Had no anchor argument at all.
        ("detect_impulse_pullback", "DetectImpulsePullbackTool", {"timeframe": "M5"}),
        # Reads candles only through two nested get_swing_levels calls.
        ("compute_fopok", "ComputeFopokTool", {"timeframe": "M15", "higher_timeframe": "H1"}),
    ],
)
async def test_tool_honours_the_context_anchor(
    recorded_requests, module: str, class_name: str, arguments: dict,
) -> None:
    import importlib

    tool = getattr(importlib.import_module(f"openforexai.tools.market.{module}"), class_name)()
    await tool.execute(dict(arguments), _context(_RecordingBus(), _ANCHOR))

    assert recorded_requests, f"{class_name} made no candle request at all"
    unanchored = [c["payload"] for c in recorded_requests if c["payload"].get("start") != _ANCHOR]
    assert unanchored == [], (
        f"{class_name} read candles without the anchor — it would show live data "
        f"at a historical simulation position: {unanchored}"
    )
