"""NotificationService — one outbound channel for agents, EC scripts and system code.

Bus member ``SYSTM-ALL___-GA-NOTIFY``, processes NOTIFY_REQUEST messages and
answers with NOTIFY_RESPONSE — same shape as RepositoryService/SemanticMemoryService.

Telegram is the first channel: an HTTPS call, so no blocking SMTP handshake, no
TLS/port/spam-filter operations, and — the actual point — a push notification on
the phone. On 2026-09-14 ten rejected orders went unnoticed for three days
because the only trace was a console buffer; a channel nobody notices is not a
channel. The transport sits behind ``_send`` so email can be added later as a
second channel rather than a parallel implementation.

Everything that makes this safe to call from anywhere lives here, in one place,
so no caller can forget it:

* **Deduplication** — the same alert repeated is counted, not resent. Our error
  log produced 136 entries in a few hours; as 136 messages the one that mattered
  would have drowned. The next real send carries the suppressed count.
* **Hourly cap** — a backstop against a flood of *distinct* messages.
* **Never raises into the caller** — a failed notification must not abort a
  trade or kill an agent cycle. Failures are reported in the response payload.
* **dry_run / disabled** — so the Prompt Workbench and tests never message a
  real chat.

Request payload::

    {"severity": "info|warning|critical", "title": str, "message": str,
     "dedup_key": str | None}
"""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import UTC, datetime
from typing import Any

from openforexai.messaging.bus import EventBus
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.utils.logging import get_logger

NOTIFICATION_SERVICE_ID = "SYSTM-ALL___-GA-NOTIFY"

_log = get_logger(__name__)

_SEVERITIES = ("info", "warning", "critical")
# Telegram rejects messages above 4096 characters outright.
_TELEGRAM_MAX_CHARS = 4096
_TRUNCATION_MARKER = "\n… (gekürzt)"
_SEVERITY_PREFIX = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}


def _is_configured(value: str) -> bool:
    """True when a config value is a real value, not an empty or unresolved one.

    load_json_config leaves ``${VAR}`` in place when the environment variable is
    missing (json_loader.py), and that literal is truthy — without this check an
    unset token would look configured and only fail at send time.
    """
    text = (value or "").strip()
    return bool(text) and not (text.startswith("${") and text.endswith("}"))


class NotificationService:
    """Single outbound notification channel with flood protection."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        dry_run: bool = False,
        bot_token: str = "",
        chat_ids: dict[str, str] | None = None,
        dedup_window_seconds: int = 900,
        max_per_hour: int = 20,
        bus: EventBus | None = None,
        monitoring_bus: Any = None,
    ) -> None:
        self._enabled = enabled
        self._dry_run = dry_run
        self._bot_token = bot_token
        self._chat_ids = chat_ids or {}
        self._dedup_window = max(int(dedup_window_seconds), 0)
        self._max_per_hour = max(int(max_per_hour), 1)
        self._bus = bus
        self._monitoring = monitoring_bus

        # dedup_key → (timestamp of last real send, suppressed since then)
        self._recent: dict[str, tuple[datetime, int]] = {}
        self._sent_times: deque[datetime] = deque()
        self._cap_notice_sent = False

        self._inbox: asyncio.Queue[AgentMessage] | None = None
        if bus is not None:
            self._inbox = bus.register_member(NOTIFICATION_SERVICE_ID)

    # ── Construction ──────────────────────────────────────────────────────────

    @classmethod
    def from_config(
        cls,
        cfg: dict[str, Any],
        bus: EventBus,
        monitoring_bus: Any = None,
    ) -> "NotificationService":
        telegram = cfg.get("telegram") if isinstance(cfg.get("telegram"), dict) else {}
        raw_chats = telegram.get("chat_ids") if isinstance(telegram.get("chat_ids"), dict) else {}
        chat_ids = {
            str(k): str(v).strip()
            for k, v in raw_chats.items()
            if _is_configured(str(v))
        }
        token = str(telegram.get("bot_token", "") or "").strip()
        if not _is_configured(token):
            token = ""

        enabled = bool(cfg.get("enable", False)) and bool(token) and bool(chat_ids)
        if bool(cfg.get("enable", False)) and not enabled:
            _log.warning(
                "Notifications enabled in config but unusable — no bot_token and/or chat_ids; "
                "staying inactive instead of failing at send time",
            )
        return cls(
            enabled=enabled,
            dry_run=bool(cfg.get("dry_run", False)),
            bot_token=token,
            chat_ids=chat_ids,
            dedup_window_seconds=int(cfg.get("dedup_window_seconds", 900) or 900),
            max_per_hour=int(cfg.get("max_per_hour", 20) or 20),
            bus=bus,
            monitoring_bus=monitoring_bus,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    async def notify(self, args: dict[str, Any]) -> dict[str, Any]:
        """Send one notification. Returns a result dict, never raises."""
        severity = str(args.get("severity", "info")).lower()
        if severity not in _SEVERITIES:
            severity = "info"
        title = str(args.get("title", "") or "").strip()
        message = str(args.get("message", "") or "").strip()
        if not title and not message:
            return {"sent": False, "reason": "empty_message"}

        dedup_key = str(args.get("dedup_key") or f"{severity}:{title}")
        now = datetime.now(UTC)

        if not self._enabled:
            return {"sent": False, "reason": "disabled"}

        suppressed_before = self._check_dedup(dedup_key, now)
        if suppressed_before is None:
            return {"sent": False, "reason": "deduplicated", "dedup_key": dedup_key}

        if not self._within_rate_limit(now):
            # One notice per window, then silence — otherwise the cap itself floods.
            if self._cap_notice_sent:
                return {"sent": False, "reason": "rate_limited"}
            self._cap_notice_sent = True
            title, message, severity = (
                "Benachrichtigungslimit erreicht",
                f"Mehr als {self._max_per_hour} Nachrichten in einer Stunde — "
                "weitere werden bis zum Abklingen unterdrückt.",
                "warning",
            )

        text = self._render(severity, title, message, suppressed_before)
        chat_id = self._chat_ids.get(severity) or self._chat_ids.get("default") or ""
        if not chat_id:
            return {"sent": False, "reason": "no_chat_for_severity", "severity": severity}

        if self._dry_run:
            _log.info("Notification (dry run)", severity=severity, title=title, chat_id=chat_id)
            self._mark_sent(dedup_key, now)
            return {"sent": False, "reason": "dry_run", "preview": text}

        try:
            await self._send(text, chat_id, silent=(severity == "info"))
        except Exception as exc:
            # Deliberately swallowed: a broken notification channel must never
            # take down the trade, script or agent cycle that triggered it.
            _log.error("Notification send failed", severity=severity, error=str(exc))
            return {"sent": False, "reason": "send_failed", "error": str(exc)}

        self._mark_sent(dedup_key, now)
        return {"sent": True, "severity": severity, "suppressed_before": suppressed_before}

    # ── Flood protection ──────────────────────────────────────────────────────

    def _check_dedup(self, key: str, now: datetime) -> int | None:
        """Return suppressed-count to report, or None when this send is suppressed."""
        entry = self._recent.get(key)
        if entry is None:
            return 0
        last_sent, suppressed = entry
        if (now - last_sent).total_seconds() < self._dedup_window:
            self._recent[key] = (last_sent, suppressed + 1)
            return None
        return suppressed

    def _mark_sent(self, key: str, now: datetime) -> None:
        self._recent[key] = (now, 0)
        self._sent_times.append(now)

    def _within_rate_limit(self, now: datetime) -> bool:
        while self._sent_times and (now - self._sent_times[0]).total_seconds() > 3600:
            self._sent_times.popleft()
        if len(self._sent_times) < self._max_per_hour:
            self._cap_notice_sent = False
            return True
        return False

    def _render(self, severity: str, title: str, message: str, suppressed: int) -> str:
        head = f"{_SEVERITY_PREFIX.get(severity, '')} {title}".strip()
        parts = [p for p in (head, message) if p]
        if suppressed:
            parts.append(f"(+{suppressed} gleichartige seither unterdrückt)")
        text = "\n\n".join(parts)
        if len(text) > _TELEGRAM_MAX_CHARS:
            text = text[: _TELEGRAM_MAX_CHARS - len(_TRUNCATION_MARKER)] + _TRUNCATION_MARKER
        return text

    # ── Channel (swap this to add email later) ────────────────────────────────

    async def _send(self, text: str, chat_id: str, *, silent: bool = False) -> None:
        import httpx

        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "disable_notification": silent,
            })
        if resp.status_code != 200:
            # Telegram puts the real reason in the body; the status alone is useless.
            raise RuntimeError(f"Telegram HTTP {resp.status_code}: {resp.text[:200]}")

    # ── Bus loop ──────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Process NOTIFY_REQUEST messages until cancelled."""
        _log.info(
            "NotificationService started",
            member_id=NOTIFICATION_SERVICE_ID,
            enabled=self._enabled,
            dry_run=self._dry_run,
        )
        while True:
            try:
                msg = await asyncio.wait_for(self._inbox.get(), timeout=1.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            if msg.event_type != EventType.NOTIFY_REQUEST:
                continue
            await self._handle(msg)

    async def _handle(self, msg: AgentMessage) -> None:
        try:
            result = await self.notify(msg.payload or {})
            error: str | None = None
        except Exception as exc:  # notify() should not raise, but never trust that here
            _log.error("NotificationService: notify failed", error=str(exc), exc_info=True)
            result, error = {"sent": False, "reason": "internal_error"}, str(exc)

        await self._bus.publish(
            AgentMessage(
                event_type=EventType.NOTIFY_RESPONSE,
                source_agent_id=NOTIFICATION_SERVICE_ID,
                target_agent_id=msg.source_agent_id,
                payload={"result": result, "error": error},
                correlation_id=str(msg.id),
            ),
            triggered_by=msg,
        )


async def notify_via_bus(
    bus: EventBus | None,
    *,
    severity: str,
    title: str,
    message: str,
    dedup_key: str | None = None,
    source_id: str = "system",
) -> None:
    """Fire-and-forget notification for internal code (watchdogs, services).

    Does not wait for a response and never raises — internal callers are usually
    already handling a problem and must not acquire a second one.
    """
    if bus is None:
        return
    try:
        await bus.publish(AgentMessage(
            event_type=EventType.NOTIFY_REQUEST,
            source_agent_id=source_id,
            target_agent_id=NOTIFICATION_SERVICE_ID,
            payload={
                "severity": severity,
                "title": title,
                "message": message,
                "dedup_key": dedup_key,
            },
        ))
    except Exception as exc:
        _log.error("Could not queue notification", title=title, error=str(exc))
