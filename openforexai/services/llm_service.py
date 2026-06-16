"""LLMService — event-bus member that wraps one LLM adapter instance.

One service is created per configured LLM module (e.g. ``azure_azmin``,
``azure_gpt4mini``, ``anthropic_claude``).  Each registers independently on
the event bus so every LLM gets its own queue and can process requests
concurrently with other LLM services.

Bus ID
------
``llm:{module_name}`` — e.g. ``llm:azure_azmin``.

Use the helper :func:`llm_service_id` to derive the ID from a module name.

Message protocol
----------------
Incoming  ``LLM_REQUEST``  payload keys:

    method          "complete_with_tools" | "complete"
    system_prompt   str
    messages        list[dict]   canonical role/content format
    tools           list[dict]   ToolSpec list (complete_with_tools only)
    user_message    str          (complete only)
    temperature     float | None
    max_tokens      int | None
    reasoning_effort str | None

Outgoing  ``LLM_RESPONSE``  payload keys:

    method          echoed from request
    content         str | None
    tool_calls      list[dict]  {id, name, arguments}
    stop_reason     str
    model           str
    input_tokens    int
    output_tokens   int
    elapsed_ms      float
    error           str | None  — set only when the LLM call raised
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from openforexai.models.messaging import AgentMessage, EventType
from openforexai.ports.llm import AbstractLLMProvider, _strip_prompt_comments, _strip_messages_comments

_log = logging.getLogger(__name__)


def llm_service_id(module_name: str) -> str:
    """Return the canonical bus ID for an LLM module: ``llm:{module_name}``."""
    return f"llm:{module_name}"


class LLMService:
    """Bus member that wraps one :class:`AbstractLLMProvider` instance.

    Call :meth:`run` as a long-running asyncio task.  The service handles
    concurrent requests by spawning a child task per message so callers never
    block each other even when one request is slow.
    """

    def __init__(
        self,
        module_name: str,
        llm: AbstractLLMProvider,
        bus: Any,
        monitoring_bus: Any = None,
    ) -> None:
        self.module_name = module_name
        self.service_id  = llm_service_id(module_name)
        self._llm         = llm
        self._bus         = bus
        self._monitoring  = monitoring_bus
        self._inbox: asyncio.Queue[AgentMessage] = bus.register_member(self.service_id)
        self._logger = _log.getChild(self.service_id)

    # ── Public ────────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Main loop — process LLM_REQUEST messages until cancelled."""
        self._logger.info(
            "LLMService started: %s  model=%s",
            self.service_id,
            self._llm.model_id,
        )
        try:
            while True:
                msg = await self._inbox.get()
                self._logger.info(
                    "LLMService received message: event_type=%s id=%s",
                    msg.event_type,
                    msg.id,
                )
                if msg.event_type != EventType.LLM_REQUEST:
                    self._logger.warning(
                        "LLMService ignoring unexpected event: %s", msg.event_type
                    )
                    continue
                # Spawn a task per request so multiple callers are served concurrently.
                # _handle catches BaseException and always publishes a response,
                # so no request is ever left without an answer.
                asyncio.create_task(
                    self._handle(msg),
                    name=f"llm-req:{self.module_name}:{msg.id}",
                )
        except asyncio.CancelledError:
            self._logger.info("LLMService stopped: %s", self.service_id)
        except Exception as exc:
            self._logger.error("LLMService crashed: %s: %s", type(exc).__name__, exc)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _handle(self, msg: AgentMessage) -> None:
        payload  = msg.payload or {}
        method   = payload.get("method", "complete_with_tools")
        started  = time.monotonic()

        try:
            if method == "complete":
                result = await self._llm.complete(
                    system_prompt    = _strip_prompt_comments(payload.get("system_prompt", "")),
                    user_message     = _strip_prompt_comments(payload.get("user_message", "")),
                    temperature      = payload.get("temperature"),
                    max_tokens       = payload.get("max_tokens"),
                    reasoning_effort = payload.get("reasoning_effort"),
                )
                response_payload: dict[str, Any] = {
                    "method":        "complete",
                    "content":       result.content,
                    "tool_calls":    [],
                    "stop_reason":   "end_turn",
                    "model":         result.model,
                    "input_tokens":  result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "elapsed_ms":    round((time.monotonic() - started) * 1000, 1),
                    "error":         None,
                }
            else:
                result = await self._llm.complete_with_tools(
                    system_prompt    = _strip_prompt_comments(payload.get("system_prompt", "")),
                    messages         = _strip_messages_comments(payload.get("messages", [])),
                    tools            = payload.get("tools", []),
                    temperature      = payload.get("temperature"),
                    max_tokens       = payload.get("max_tokens"),
                    reasoning_effort = payload.get("reasoning_effort"),
                )
                response_payload = {
                    "method":        "complete_with_tools",
                    "content":       result.content,
                    "tool_calls":    [
                        {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                        for tc in result.tool_calls
                    ],
                    "stop_reason":   result.stop_reason,
                    "model":         result.model,
                    "input_tokens":  result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "elapsed_ms":    round((time.monotonic() - started) * 1000, 1),
                    "error":         None,
                }

        except BaseException as exc:
            # BaseException catches CancelledError too — always send a response
            # so the caller's future is resolved (not left hanging).
            self._logger.error(
                "LLM call failed [%s]: %s: %s",
                self.module_name, type(exc).__name__, exc,
            )
            response_payload = {
                "method":        method,
                "content":       None,
                "tool_calls":    [],
                "stop_reason":   "error",
                "model":         "",
                "input_tokens":  0,
                "output_tokens": 0,
                "elapsed_ms":    round((time.monotonic() - started) * 1000, 1),
                "error":         f"{type(exc).__name__}: {exc}",
            }
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise  # let these propagate

        # correlation_id must be str(msg.id) — the request message ID.
        # The caller registered the future under str(msg.id) (same pattern as bus_request).
        await self._bus.publish(AgentMessage(
            event_type       = EventType.LLM_RESPONSE,
            source_agent_id  = self.service_id,
            target_agent_id  = msg.source_agent_id,
            payload          = response_payload,
            correlation_id   = str(msg.id),
        ))
