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
from openforexai.services.notification_rules import (
    dedup_key_for,
    event_view,
    render,
    rule_applies,
)
from openforexai.utils.logging import get_logger

NOTIFICATION_SERVICE_ID = "SYSTM-ALL___-GA-NOTIFY"

_log = get_logger(__name__)

_SEVERITIES = ("info", "warning", "critical")
# Telegram rejects messages above 4096 characters outright.
_TELEGRAM_MAX_CHARS = 4096
_TRUNCATION_MARKER = "\n… (truncated)"
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
        rules: dict[str, Any] | None = None,
        bus: EventBus | None = None,
        monitoring_bus: Any = None,
    ) -> None:
        self._enabled = enabled
        self._dry_run = dry_run
        self._bot_token = bot_token
        self._chat_ids = chat_ids or {}
        self._rules = rules or {}
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

    @staticmethod
    def _settings_from_config(cfg: dict[str, Any]) -> dict[str, Any]:
        """Parse the notifications config block into constructor keyword arguments.

        Shared by from_config and apply_config so a saved config change is
        interpreted exactly like a fresh start — the project rule is that config
        takes effect without a restart, and two parsers would eventually disagree.
        """
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
        return {
            "enabled": enabled,
            "dry_run": bool(cfg.get("dry_run", False)),
            "bot_token": token,
            "chat_ids": chat_ids,
            "dedup_window_seconds": int(cfg.get("dedup_window_seconds", 900) or 900),
            "max_per_hour": int(cfg.get("max_per_hour", 20) or 20),
            "rules": cfg.get("rules") if isinstance(cfg.get("rules"), dict) else {},
        }

    @classmethod
    def from_config(
        cls,
        cfg: dict[str, Any],
        bus: EventBus,
        monitoring_bus: Any = None,
    ) -> "NotificationService":
        return cls(**cls._settings_from_config(cfg), bus=bus, monitoring_bus=monitoring_bus)

    def apply_config(self, cfg: dict[str, Any]) -> None:
        """Adopt a changed notifications config without restarting.

        Deliberately keeps the dedup and rate-limit state: an edit to one rule
        is not a reason to let every already-suppressed message through again.
        """
        settings = self._settings_from_config(cfg)
        self._enabled = settings["enabled"]
        self._dry_run = settings["dry_run"]
        self._bot_token = settings["bot_token"]
        self._chat_ids = settings["chat_ids"]
        self._dedup_window = max(int(settings["dedup_window_seconds"]), 0)
        self._max_per_hour = max(int(settings["max_per_hour"]), 1)
        self._rules = settings["rules"]
        _log.info("Notification config applied", enabled=self._enabled, rules=len(self._rules))

    @property
    def rules(self) -> dict[str, Any]:
        return dict(self._rules)

    # ── Rules ─────────────────────────────────────────────────────────────────

    @staticmethod
    def rule_event(name: str, rule: dict[str, Any]) -> str:
        """Which bus event a rule reacts to.

        Rules are keyed by a free name so several can react to the same event —
        a rejected order and a filled one deserve different messages, and a
        monitoring filter forwarded from the console needs its own entry
        alongside any other on ``system_alert``.

        Older configurations keyed rules by the event type itself and carry no
        ``event`` field; for those the key *is* the event, so they keep working
        untouched.
        """
        declared = rule.get("event")
        if isinstance(declared, str) and declared.strip():
            return declared.strip()
        return name

    def rules_for(self, event_type: str) -> list[tuple[str, dict[str, Any]]]:
        """Every rule reacting to *event_type*, in a stable order."""
        return [
            (name, rule)
            for name, rule in sorted(self._rules.items())
            if isinstance(rule, dict) and self.rule_event(name, rule) == event_type
        ]

    def rule_event_types(self) -> set[str]:
        """The distinct bus events any rule listens to."""
        return {
            self.rule_event(name, rule)
            for name, rule in self._rules.items()
            if isinstance(rule, dict)
        }

    # ── Derived routing ───────────────────────────────────────────────────────

    ROUTING_OWNER = "telegram"

    async def sync_routing_rules(self, store: Any) -> int:
        """Make sure every configured rule's event actually reaches this service.

        Without this a warning needs two entries that must agree — miss the
        routing half and the event never arrives, miss the rule half and it is
        discarded on arrival. Both fail silently, which is the one failure mode
        an alerting channel must not have. Deriving the routing from the rules
        leaves a single place to configure.
        """
        from openforexai.messaging.routing import RoutingRule

        derived = [
            RoutingRule(
                id=f"notify_{event_type}",
                description=f"{event_type} → NotificationService (abgeleitet aus notifications.rules)",
                event=event_type,
                from_pattern="*",
                to=NOTIFICATION_SERVICE_ID,
                priority=50,
                owner=self.ROUTING_OWNER,
            )
            for event_type in sorted(self.rule_event_types())
        ]
        return await store.replace_owner(self.ROUTING_OWNER, derived)

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
                "Notification limit reached",
                f"More than {self._max_per_hour} messages within an hour — "
                "further ones are suppressed until it subsides.",
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
            parts.append(f"(+{suppressed} of the same kind suppressed since)")
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

            if msg.event_type == EventType.NOTIFY_REQUEST:
                await self._handle(msg)
            else:
                # Anything else only arrives here because a routing rule sent it
                # (config/RunTime/event_routing.json5) — turn it into a
                # notification if a rule covers it, otherwise ignore it quietly.
                await self._handle_routed_event(msg)

    async def _handle_routed_event(self, msg: AgentMessage) -> None:
        """Apply the configured rules to a plain bus event. Never answers."""
        event_type = str(getattr(msg.event_type, "value", msg.event_type))
        matching = self.rules_for(event_type)
        if not matching:
            return

        data = event_view(event_type, msg.source_agent_id, msg.instrument, msg.payload)
        for name, rule in matching:
            try:
                if not rule_applies(rule, data):
                    continue
                args = {
                    "severity": rule.get("severity", "warning"),
                    "title": render(str(rule.get("title") or event_type), data),
                    "message": render(str(rule.get("template") or ""), data),
                    # Keyed by rule name, not event type: two rules on the same
                    # event must not suppress each other through a shared key.
                    "dedup_key": dedup_key_for(name, rule, data),
                }
            except Exception as exc:
                # A malformed rule must not silence the others on the same event.
                _log.error("Notification rule failed", rule=name, event=event_type, error=str(exc))
                continue
            await self.notify(args)

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
