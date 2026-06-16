"""LLM bus-request helpers.

These functions allow any bus member (agents, EC scripts, management API)
to send an LLM request through the event bus and await the response — without
holding a direct reference to any LLM adapter.

Usage (in agents or tools)::

    from openforexai.messaging.llm_helpers import llm_complete_with_tools, llm_complete

    response = await llm_complete_with_tools(
        event_bus    = self._bus,
        llm_name     = "azure_azmin",
        source_id    = self.agent_id,
        system_prompt= "...",
        messages     = messages,
        tools        = tool_specs,
        temperature  = 0.2,
        max_tokens   = 4096,
    )

Usage in EC scripts (injected as ``ask_llm``)::

    response = await ask_llm("azure_azmin", "Analyse EURUSD trend.")
    response = await ask_llm("azure_gpt4mini", messages=[...], tools=[...])
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from openforexai.models.messaging import AgentMessage, EventType
from openforexai.ports.llm import LLMResponse, LLMResponseWithTools, ToolCall
from openforexai.services.llm_service import llm_service_id

_DEFAULT_TOOL_TIMEOUT   = 180.0
_DEFAULT_SIMPLE_TIMEOUT = 180.0


# ── Core helpers ──────────────────────────────────────────────────────────────

async def llm_complete_with_tools(
    event_bus:         Any,
    llm_name:          str,
    source_id:         str,
    system_prompt:     str,
    messages:          list[dict[str, Any]],
    tools:             list[dict[str, Any]],
    temperature:       float | None = None,
    max_tokens:        int   | None = None,
    reasoning_effort:  str   | None = None,
    timeout:           float        = _DEFAULT_TOOL_TIMEOUT,
) -> LLMResponseWithTools:
    """Send a *complete_with_tools* request to ``llm:{llm_name}`` on the bus.

    Publishes ``LLM_REQUEST``, waits for ``LLM_RESPONSE`` via the correlation-ID
    future mechanism, and returns a :class:`LLMResponseWithTools` object.

    Raises :class:`RuntimeError` if the LLM Service reports an error.
    Raises :class:`asyncio.TimeoutError` if no response arrives within *timeout* seconds.
    """
    target = llm_service_id(llm_name)
    future: asyncio.Future = asyncio.get_running_loop().create_future()

    # Use msg.id as the future key — same pattern as bus_request() in tools/base.py.
    # Do NOT set correlation_id on the request itself; that would cause the bus to
    # resolve the future immediately when the request is dispatched.
    msg = AgentMessage(
        event_type      = EventType.LLM_REQUEST,
        source_agent_id = source_id,
        target_agent_id = target,
        payload         = {
            "method":           "complete_with_tools",
            "system_prompt":    system_prompt,
            "messages":         messages,
            "tools":            tools,
            "temperature":      temperature,
            "max_tokens":       max_tokens,
            "reasoning_effort": reasoning_effort,
        },
    )
    future_key = str(msg.id)
    event_bus.register_response_future(future_key, future)
    try:
        await event_bus.publish(msg)
        resp_payload: dict[str, Any] = await asyncio.wait_for(
            asyncio.shield(future), timeout=timeout
        )
    except asyncio.TimeoutError:
        event_bus.cancel_response_future(future_key)
        raise

    if resp_payload.get("error"):
        raise RuntimeError(
            f"LLM '{llm_name}' returned error: {resp_payload['error']}"
        )

    return _payload_to_response_with_tools(resp_payload)


async def llm_complete(
    event_bus:         Any,
    llm_name:          str,
    source_id:         str,
    system_prompt:     str,
    user_message:      str,
    temperature:       float | None = None,
    max_tokens:        int   | None = None,
    reasoning_effort:  str   | None = None,
    timeout:           float        = _DEFAULT_SIMPLE_TIMEOUT,
) -> LLMResponse:
    """Send a simple *complete* request (no tools) to ``llm:{llm_name}`` on the bus."""
    target = llm_service_id(llm_name)
    future: asyncio.Future = asyncio.get_running_loop().create_future()

    msg = AgentMessage(
        event_type      = EventType.LLM_REQUEST,
        source_agent_id = source_id,
        target_agent_id = target,
        payload         = {
            "method":           "complete",
            "system_prompt":    system_prompt,
            "user_message":     user_message,
            "temperature":      temperature,
            "max_tokens":       max_tokens,
            "reasoning_effort": reasoning_effort,
        },
    )
    future_key = str(msg.id)
    event_bus.register_response_future(future_key, future)
    try:
        await event_bus.publish(msg)
        resp_payload: dict[str, Any] = await asyncio.wait_for(
            asyncio.shield(future), timeout=timeout
        )
    except asyncio.TimeoutError:
        event_bus.cancel_response_future(future_key)
        raise

    if resp_payload.get("error"):
        raise RuntimeError(
            f"LLM '{llm_name}' returned error: {resp_payload['error']}"
        )

    return LLMResponse(
        content      = resp_payload.get("content") or "",
        model        = resp_payload.get("model", ""),
        input_tokens = resp_payload.get("input_tokens", 0),
        output_tokens= resp_payload.get("output_tokens", 0),
        raw          = resp_payload,
    )


# ── EC-script friendly wrapper ────────────────────────────────────────────────

def make_ask_llm(event_bus: Any, source_id: str):
    """Return a bound ``ask_llm`` coroutine for use inside EC scripts.

    Inject the returned function into the script execution context so scripts
    never need a direct reference to the event bus::

        # in composer.py:
        script_globals["ask_llm"] = make_ask_llm(self._bus, self.ec_id)

    Script usage::

        # Single user message (simple completion)
        response = await ask_llm("azure_azmin", "What is the EURUSD trend?")

        # Full tool-use conversation
        response = await ask_llm(
            "azure_gpt4mini",
            messages     = [{"role": "user", "content": "..."}],
            system_prompt= "You are a Forex expert.",
            tools        = [...],
        )

    Returns a :class:`LLMResponseWithTools` in all cases.
    ``response.content``   — text reply (may be None when tool_calls present).
    ``response.tool_calls``— list of :class:`ToolCall` (may be empty).
    ``response.stop_reason``— "end_turn" | "tool_use" | "error".
    """

    async def ask_llm(
        llm_name:      str,
        messages:      list[dict[str, Any]] | str | None = None,
        *,
        system_prompt: str                  = "",
        tools:         list[dict[str, Any]] | None = None,
        temperature:   float | None         = None,
        max_tokens:    int   | None         = None,
        timeout:       float                = _DEFAULT_TOOL_TIMEOUT,
    ) -> LLMResponseWithTools:
        # Allow shorthand: ask_llm("azure_azmin", "single user message")
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        if messages is None:
            messages = []

        return await llm_complete_with_tools(
            event_bus        = event_bus,
            llm_name         = llm_name,
            source_id        = source_id,
            system_prompt    = system_prompt,
            messages         = messages,
            tools            = tools or [],
            temperature      = temperature,
            max_tokens       = max_tokens,
            timeout          = timeout,
        )

    return ask_llm


# ── Deserialization helpers ───────────────────────────────────────────────────

def _payload_to_response_with_tools(payload: dict[str, Any]) -> LLMResponseWithTools:
    tool_calls = [
        ToolCall(
            id        = tc["id"],
            name      = tc["name"],
            arguments = tc.get("arguments", {}),
        )
        for tc in payload.get("tool_calls", [])
    ]
    return LLMResponseWithTools(
        content       = payload.get("content"),
        tool_calls    = tool_calls,
        stop_reason   = payload.get("stop_reason", "end_turn"),
        model         = payload.get("model", ""),
        input_tokens  = payload.get("input_tokens", 0),
        output_tokens = payload.get("output_tokens", 0),
        raw           = payload,
    )
