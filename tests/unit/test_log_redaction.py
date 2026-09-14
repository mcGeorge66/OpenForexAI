"""Credentials must never reach a log file.

Telegram requires the bot token inside the URL path and HTTP clients log URLs,
so "POST https://api.telegram.org/bot<token>/sendMessage" would write the secret
to disk on every notification. Whoever holds that token can send convincing fake
alerts through the very channel the operator trusts.
"""
from __future__ import annotations

import logging

from openforexai.utils.logging import _RedactSecrets

_TOKEN = "8123456789:AAH7xSomeExampleTokenValue_ForTests-1234"


def _record(msg: str, *args) -> logging.LogRecord:
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, args, None)


def _filtered(msg: str, *args) -> str:
    rec = _record(msg, *args)
    _RedactSecrets().filter(rec)
    return rec.getMessage()


def test_bot_token_in_url_is_redacted():
    out = _filtered(f'HTTP Request: POST https://api.telegram.org/bot{_TOKEN}/sendMessage "200 OK"')
    assert _TOKEN not in out
    assert "/bot<redacted>/sendMessage" in out


def test_redaction_also_applies_to_formatted_arguments():
    """httpx logs via %-args, so the secret is not in record.msg itself."""
    out = _filtered("HTTP Request: %s", f"POST https://api.telegram.org/bot{_TOKEN}/getUpdates")
    assert _TOKEN not in out


def test_other_urls_are_left_alone():
    msg = "HTTP Request: POST https://api.example.com/v1/chat/completions"
    assert _filtered(msg) == msg


def test_filter_keeps_the_record():
    """Redaction must never drop a log line — only rewrite it."""
    assert _RedactSecrets().filter(_record("harmless")) is True


def test_unformattable_record_does_not_raise():
    """A broken log call must not take down logging itself."""
    rec = _record("%s %s", "only-one-arg")
    assert _RedactSecrets().filter(rec) is True
