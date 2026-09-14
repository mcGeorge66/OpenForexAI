"""The notification channel must protect the mailbox and never break its caller.

A channel that floods gets muted, and a muted channel is the same as no channel —
which is how ten rejected orders stayed unnoticed for three days on 2026-09-14.
These tests pin the parts that make it trustworthy: deduplication, the hourly
cap, dry-run, and that a broken transport is reported rather than raised.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from openforexai.services.notification_service import NotificationService


def _service(**overrides) -> NotificationService:
    kwargs = dict(
        enabled=True,
        dry_run=False,
        bot_token="test-token",
        chat_ids={"default": "111", "critical": "999"},
        dedup_window_seconds=900,
        max_per_hour=20,
    )
    kwargs.update(overrides)
    svc = NotificationService(**kwargs)
    svc.sent: list[tuple[str, str, bool]] = []  # type: ignore[attr-defined]

    async def _fake_send(text, chat_id, *, silent=False):
        svc.sent.append((text, chat_id, silent))

    svc._send = _fake_send  # type: ignore[assignment]
    return svc


async def test_sends_to_the_chat_for_its_severity():
    svc = _service()

    result = await svc.notify({"severity": "critical", "title": "Order abgelehnt", "message": "10x"})

    assert result["sent"] is True
    text, chat_id, silent = svc.sent[0]
    assert chat_id == "999"          # critical has its own chat
    assert "Order abgelehnt" in text
    assert silent is False


async def test_info_falls_back_to_default_chat_and_is_silent():
    svc = _service()

    await svc.notify({"severity": "info", "title": "Tagesbericht", "message": "alles ruhig"})

    _, chat_id, silent = svc.sent[0]
    assert chat_id == "111"
    assert silent is True            # routine info must not buzz the phone


async def test_identical_message_is_suppressed_within_the_window():
    svc = _service()
    payload = {"severity": "warning", "title": "Stale", "message": "EA-EXAM"}

    first = await svc.notify(payload)
    second = await svc.notify(payload)

    assert first["sent"] is True
    assert second["sent"] is False
    assert second["reason"] == "deduplicated"
    assert len(svc.sent) == 1


async def test_suppressed_count_is_reported_on_the_next_real_send():
    svc = _service(dedup_window_seconds=0)  # window closed → next send goes out
    payload = {"severity": "warning", "title": "Stale", "message": "EA-EXAM", "dedup_key": "k"}

    await svc.notify(payload)
    svc._recent["k"] = (datetime.now(UTC) - timedelta(hours=1), 17)  # 17 piled up
    await svc.notify(payload)

    assert "+17" in svc.sent[-1][0]


async def test_different_messages_are_not_deduplicated():
    svc = _service()

    await svc.notify({"severity": "warning", "title": "A", "message": "x"})
    await svc.notify({"severity": "warning", "title": "B", "message": "y"})

    assert len(svc.sent) == 2


async def test_hourly_cap_stops_a_flood_after_one_notice():
    svc = _service(max_per_hour=3, dedup_window_seconds=0)

    for i in range(6):
        await svc.notify({"severity": "warning", "title": f"T{i}", "message": "m"})

    # 3 real messages + exactly one "cap reached" notice, then silence.
    assert len(svc.sent) == 4
    assert "limit" in svc.sent[-1][0].lower()


async def test_disabled_service_reports_instead_of_sending():
    svc = _service(enabled=False)

    result = await svc.notify({"severity": "critical", "title": "X", "message": "y"})

    assert result == {"sent": False, "reason": "disabled"}
    assert svc.sent == []


async def test_dry_run_previews_without_sending():
    svc = _service(dry_run=True)

    result = await svc.notify({"severity": "warning", "title": "X", "message": "y"})

    assert result["sent"] is False
    assert result["reason"] == "dry_run"
    assert "X" in result["preview"]
    assert svc.sent == []


async def test_transport_failure_is_reported_not_raised():
    """A broken channel must never abort the trade or cycle that triggered it."""
    svc = _service()

    async def _boom(text, chat_id, *, silent=False):
        raise RuntimeError("Telegram HTTP 502")

    svc._send = _boom  # type: ignore[assignment]

    result = await svc.notify({"severity": "critical", "title": "X", "message": "y"})

    assert result["sent"] is False
    assert result["reason"] == "send_failed"
    assert "502" in result["error"]


async def test_long_message_is_truncated_to_telegram_limit():
    svc = _service()

    await svc.notify({"severity": "info", "title": "T", "message": "x" * 9000})

    assert len(svc.sent[0][0]) <= 4096
    assert svc.sent[0][0].endswith("(gekürzt)")


async def test_unresolved_env_placeholder_counts_as_unconfigured():
    """An unset env var leaves "${VAR}" in the config — truthy, but useless."""
    svc = NotificationService.from_config(
        {"enable": True, "telegram": {"bot_token": "${OFAI_TELEGRAM_BOT_TOKEN}",
                                      "chat_ids": {"default": "111"}}},
        bus=None,
    )

    assert await svc.notify({"severity": "critical", "title": "X", "message": "y"}) == {
        "sent": False, "reason": "disabled",
    }


async def test_enable_without_chat_ids_stays_inactive():
    svc = NotificationService.from_config(
        {"enable": True, "telegram": {"bot_token": "real-token", "chat_ids": {}}},
        bus=None,
    )

    result = await svc.notify({"severity": "warning", "title": "X", "message": "y"})

    assert result["reason"] == "disabled"


@pytest.mark.parametrize("severity", ["bogus", "", None])
async def test_unknown_severity_falls_back_to_info(severity):
    svc = _service()

    await svc.notify({"severity": severity, "title": "T", "message": "m"})

    assert svc.sent[0][1] == "111"   # default chat, i.e. treated as info
