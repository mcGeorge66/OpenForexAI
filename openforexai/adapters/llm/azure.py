from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openai import AsyncAzureOpenAI

from openforexai.adapters.llm.base import llm_retry
from openforexai.ports.llm import (
    AbstractLLMProvider,
    LLMResponse,
    LLMResponseWithTools,
    ToolCall,
    ToolSpec,
)


def _to_openai_tool(spec: ToolSpec) -> dict:
    """Convert canonical ToolSpec (Anthropic-style) to OpenAI function format."""
    return {
        "type": "function",
        "function": {
            "name": spec["name"],
            "description": spec.get("description", ""),
            "parameters": spec.get("input_schema", {"type": "object", "properties": {}}),
        },
    }


class AzureOpenAILLMProvider(AbstractLLMProvider):
    """Azure OpenAI adapter using the OpenAI SDK's AzureOpenAI client."""

    @staticmethod
    def _require_config_value(cfg: dict[str, Any], key: str) -> Any:
        if key not in cfg:
            raise ValueError(
                f"Azure LLM config is missing required key '{key}'. "
                "Operational LLM settings must be defined in the module config."
            )
        return cfg[key]

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        deployment: str,
        api_version: str = "2024-12-01-preview",
        model: str | None = None,
        retry_attempts: int = 3,
        retry_base_delay: float = 1.0,
        timeout_seconds: float = 30.0,
        sdk_max_retries: int = 0,
        transcript_enabled: bool = False,
        transcript_path: str | None = None,
        default_temperature: float | None = None,
        default_max_tokens: int = 4096,
        reasoning_effort: str | None = None,
        verbosity: str | None = None,
    ) -> None:
        # Azure routes requests by deployment name; model_id is used for logging only
        self._deployment = deployment
        self._model = model or deployment
        self._retry_attempts = retry_attempts
        self._retry_base_delay = retry_base_delay
        self._client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
            timeout=timeout_seconds,
            max_retries=sdk_max_retries,
        )
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens
        self._reasoning_effort = reasoning_effort
        self._verbosity = verbosity
        self._debug_diagnostics_callback = None
        self._debug_diagnostics_context: dict[str, Any] = {}
        self._transcript_enabled = bool(transcript_enabled)
        self._transcript_base_path = self._resolve_transcript_path(transcript_path)
        self._transcript_lock = asyncio.Lock()
        # Track the date last written so we can prune old files on rollover only
        self._transcript_last_date: str | None = None
        # Keep at most this many dated transcript files in the directory
        self._transcript_max_files = 10

    @classmethod
    def from_config(cls, cfg: dict) -> AzureOpenAILLMProvider:
        transcript_enabled = bool(cls._require_config_value(cfg, "transcript_enabled"))
        transcript_path = cfg.get("transcript_path")
        if transcript_enabled and not isinstance(transcript_path, str):
            raise ValueError(
                "Azure LLM config must define 'transcript_path' when 'transcript_enabled' is true."
            )
        temperature = cfg.get("temperature")
        if temperature is not None and not isinstance(temperature, (int, float)):
            raise ValueError("Azure LLM config key 'temperature' must be numeric when provided.")
        # Reasoning-model controls (GPT-5 family). Optional — only sent if configured.
        reasoning_effort = cfg.get("reasoning_effort")
        if reasoning_effort is not None:
            if not isinstance(reasoning_effort, str):
                raise ValueError("Azure LLM config key 'reasoning_effort' must be a string when provided.")
            allowed_efforts = {"minimal", "low", "medium", "high"}
            if reasoning_effort not in allowed_efforts:
                raise ValueError(
                    f"Azure LLM config key 'reasoning_effort' must be one of {sorted(allowed_efforts)}, "
                    f"got {reasoning_effort!r}."
                )
        verbosity = cfg.get("verbosity")
        if verbosity is not None:
            if not isinstance(verbosity, str):
                raise ValueError("Azure LLM config key 'verbosity' must be a string when provided.")
            allowed_verbosity = {"low", "medium", "high"}
            if verbosity not in allowed_verbosity:
                raise ValueError(
                    f"Azure LLM config key 'verbosity' must be one of {sorted(allowed_verbosity)}, "
                    f"got {verbosity!r}."
                )
        return cls(
            api_key=cls._require_config_value(cfg, "api_key"),
            endpoint=cls._require_config_value(cfg, "endpoint"),
            deployment=cls._require_config_value(cfg, "deployment"),
            api_version=cls._require_config_value(cfg, "api_version"),
            model=cfg.get("model") or cls._require_config_value(cfg, "deployment"),
            retry_attempts=cls._require_config_value(cfg, "retry_attempts"),
            retry_base_delay=cls._require_config_value(cfg, "retry_base_delay"),
            timeout_seconds=cls._require_config_value(cfg, "timeout_seconds"),
            sdk_max_retries=cls._require_config_value(cfg, "sdk_max_retries"),
            transcript_enabled=transcript_enabled,
            transcript_path=transcript_path,
            default_temperature=temperature,
            default_max_tokens=cls._require_config_value(cfg, "max_tokens"),
            reasoning_effort=reasoning_effort,
            verbosity=verbosity,
        )

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def default_temperature(self) -> float | None:
        return self._default_temperature

    @property
    def default_max_tokens(self) -> int:
        return self._default_max_tokens

    def set_debug_diagnostics(
        self,
        callback=None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self._debug_diagnostics_callback = callback
        self._debug_diagnostics_context = dict(context or {})

    def _emit_debug_diagnostic(self, event_name: str, **payload: Any) -> None:
        if self._debug_diagnostics_callback is None:
            return
        merged = dict(self._debug_diagnostics_context)
        merged.update(payload)
        self._debug_diagnostics_callback(event_name, merged)

    @staticmethod
    def _resolve_transcript_path(raw_path: str | None) -> Path | None:
        if not isinstance(raw_path, str) or not raw_path.strip():
            return None
        path = Path(raw_path.strip())
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()

    @staticmethod
    def _serialize_json_payload(payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        return json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))

    async def _write_transcript_record(
        self,
        *,
        direction: str,
        operation: str,
        attempt: int | None,
        attempts_total: int | None,
        payload: Any,
        content_type: str = "application/json",
        error_type: str | None = None,
    ) -> None:
        if not getattr(self, "_transcript_enabled", False) or getattr(self, "_transcript_base_path", None) is None:
            return

        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        sender = "openforexai" if direction == "request" else "azure_openai"
        receiver = "azure_openai" if direction == "request" else "openforexai"
        raw_payload = self._serialize_json_payload(payload)

        header_lines = [
            "=" * 120,
            f"timestamp: {timestamp}",
            f"sender: {sender}",
            f"receiver: {receiver}",
            f"direction: {direction}",
            f"operation: {operation}",
        ]
        context = self._debug_diagnostics_context
        if "agent_id" in context:
            header_lines.append(f"agent_id: {context['agent_id']}")
        if "turn" in context:
            header_lines.append(f"turn: {context['turn']}")
        if "trigger" in context and context["trigger"] is not None:
            header_lines.append(f"trigger: {context['trigger']}")
        if attempt is not None:
            header_lines.append(f"attempt: {attempt}")
        if attempts_total is not None:
            header_lines.append(f"attempts_total: {attempts_total}")
        if error_type:
            header_lines.append(f"error_type: {error_type}")
        header_lines.extend([
            f"model: {self._deployment}",
            f"content_type: {content_type}",
            "-" * 120,
            raw_payload,
            "",
        ])
        record = "\n".join(header_lines)

        async with self._transcript_lock:
            await asyncio.to_thread(self._append_transcript_text, record)

    def _schedule_transcript_record(self, **kwargs: Any) -> None:
        if not getattr(self, "_transcript_enabled", False) or getattr(self, "_transcript_base_path", None) is None:
            return
        asyncio.create_task(self._write_transcript_record(**kwargs))

    def _today_transcript_path(self) -> Path | None:
        """Return today's dated transcript file path.

        Base path 'logs/azure_llm_transcript.log' becomes
        'logs/azure_llm_transcript_YYYY-MM-DD.log' for today's UTC date.
        """
        base = self._transcript_base_path
        if base is None:
            return None
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        return base.with_name(f"{base.stem}_{date_str}{base.suffix}")

    def _prune_old_transcript_files(self) -> None:
        """Delete the oldest dated transcript files, keeping only the newest N.

        Files are matched by glob '<stem>_*<suffix>' in the parent directory and
        sorted by filename (ISO date prefix sorts chronologically). The newest
        ``_transcript_max_files`` are retained, the rest are removed.
        """
        base = self._transcript_base_path
        if base is None:
            return
        try:
            parent = base.parent
            if not parent.exists():
                return
            pattern = f"{base.stem}_*{base.suffix}"
            files = sorted(parent.glob(pattern), key=lambda p: p.name, reverse=True)
            for old in files[self._transcript_max_files:]:
                try:
                    old.unlink()
                except OSError:
                    pass
        except OSError:
            pass

    def _append_transcript_text(self, text: str) -> None:
        target = self._today_transcript_path()
        if target is None:
            return
        # On day rollover, prune old files (cheap: runs at most once per day per process)
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if self._transcript_last_date != today:
            self._transcript_last_date = today
            self._prune_old_transcript_files()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(text)

    # ── Simple completions ────────────────────────────────────────────────────

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        resolved_temp = self._default_temperature if temperature is None else temperature
        resolved_max_tokens = self._default_max_tokens if max_tokens is None else max_tokens
        resolved_reasoning = self._reasoning_effort if reasoning_effort is None else reasoning_effort

        async def _call() -> LLMResponse:
            kwargs: dict[str, Any] = {
                "model": self._deployment,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            }
            if resolved_temp is not None:
                kwargs["temperature"] = resolved_temp
            if resolved_max_tokens is not None:
                kwargs["max_completion_tokens"] = resolved_max_tokens
            if resolved_reasoning is not None:
                kwargs["reasoning_effort"] = resolved_reasoning
            if self._verbosity is not None:
                kwargs["verbosity"] = self._verbosity
            await self._write_transcript_record(
                direction="request",
                operation="complete",
                attempt=None,
                attempts_total=None,
                payload=kwargs,
            )
            resp = await self._client.chat.completions.create(**kwargs)
            await self._write_transcript_record(
                direction="response",
                operation="complete",
                attempt=None,
                attempts_total=None,
                payload=resp.model_dump(),
            )
            choice = resp.choices[0]
            return LLMResponse(
                content=choice.message.content or "",
                model=resp.model,
                input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
                output_tokens=resp.usage.completion_tokens if resp.usage else 0,
                raw=resp.model_dump(),
            )

        return await llm_retry(
            _call,
            attempts=self._retry_attempts,
            base_delay=self._retry_base_delay,
            on_attempt_start=lambda attempt, total: self._emit_debug_diagnostic(
                "llm_http_attempt_started",
                operation="complete",
                attempt=attempt,
                attempts_total=total,
            ),
            on_attempt_success=lambda attempt, total, elapsed_ms: self._emit_debug_diagnostic(
                "llm_http_attempt_completed",
                operation="complete",
                attempt=attempt,
                attempts_total=total,
                elapsed_ms=round(elapsed_ms, 1),
            ),
            on_attempt_error=lambda attempt, total, elapsed_ms, exc: self._emit_debug_diagnostic(
                "llm_http_attempt_failed",
                operation="complete",
                attempt=attempt,
                attempts_total=total,
                elapsed_ms=round(elapsed_ms, 1),
                error_type=type(exc).__name__,
                error=str(exc),
            ),
        )

    async def complete_structured(
        self,
        system_prompt: str,
        user_message: str,
        response_schema: type,
    ) -> dict[str, Any]:
        schema = response_schema.model_json_schema()
        augmented_prompt = (
            f"{system_prompt}\n\nRespond ONLY with valid JSON matching this schema:\n"
            f"{json.dumps(schema, indent=2)}"
        )
        response = await self.complete(
            system_prompt=augmented_prompt,
            user_message=user_message,
            temperature=0.0,
        )
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        return json.loads(raw)

    # ── Tool-use completions ──────────────────────────────────────────────────

    async def complete_with_tools(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
    ) -> LLMResponseWithTools:
        """Single turn using Azure OpenAI's native function-calling API."""
        openai_tools = [_to_openai_tool(t) for t in tools]
        full_messages = [{"role": "system", "content": system_prompt}] + [
            self._sanitize_message(m) for m in messages
        ]

        resolved_temp = self._default_temperature if temperature is None else temperature
        resolved_max_tokens = self._default_max_tokens if max_tokens is None else max_tokens
        resolved_reasoning = self._reasoning_effort if reasoning_effort is None else reasoning_effort
        current_attempt = 0
        attempts_total = self._retry_attempts

        def _set_current_attempt(attempt: int) -> None:
            nonlocal current_attempt
            current_attempt = attempt

        def _on_with_tools_attempt_start(attempt: int, total: int) -> None:
            _set_current_attempt(attempt)
            self._emit_debug_diagnostic(
                "llm_http_attempt_started",
                operation="complete_with_tools",
                call_mode="with_tools",
                attempt=attempt,
                attempts_total=total,
                message_count=len(full_messages),
                tool_count=len(openai_tools),
            )

        def _on_with_tools_attempt_success(attempt: int, total: int, elapsed_ms: float) -> None:
            self._emit_debug_diagnostic(
                "llm_http_attempt_completed",
                operation="complete_with_tools",
                call_mode="with_tools",
                attempt=attempt,
                attempts_total=total,
                elapsed_ms=round(elapsed_ms, 1),
                message_count=len(full_messages),
                tool_count=len(openai_tools),
            )

        def _on_with_tools_attempt_error(
            attempt: int,
            total: int,
            elapsed_ms: float,
            exc: Exception,
        ) -> None:
            self._emit_debug_diagnostic(
                "llm_http_attempt_failed",
                operation="complete_with_tools",
                call_mode="with_tools",
                attempt=attempt,
                attempts_total=total,
                elapsed_ms=round(elapsed_ms, 1),
                message_count=len(full_messages),
                tool_count=len(openai_tools),
                error_type=type(exc).__name__,
                error=str(exc),
            )
            self._schedule_transcript_record(
                direction="response",
                operation="complete_with_tools_error",
                attempt=attempt,
                attempts_total=total,
                payload={"error_type": type(exc).__name__, "error": str(exc)},
                content_type="application/json",
                error_type=type(exc).__name__,
            )

        def _on_fallback_attempt_start(attempt: int, total: int) -> None:
            _set_current_attempt(attempt)
            self._emit_debug_diagnostic(
                "llm_http_attempt_started",
                operation="complete_with_tools",
                call_mode="without_tools_fallback",
                attempt=attempt,
                attempts_total=total,
                message_count=len(full_messages),
                tool_count=0,
            )

        def _on_fallback_attempt_success(attempt: int, total: int, elapsed_ms: float) -> None:
            self._emit_debug_diagnostic(
                "llm_http_attempt_completed",
                operation="complete_with_tools",
                call_mode="without_tools_fallback",
                attempt=attempt,
                attempts_total=total,
                elapsed_ms=round(elapsed_ms, 1),
                message_count=len(full_messages),
                tool_count=0,
            )

        def _on_fallback_attempt_error(
            attempt: int,
            total: int,
            elapsed_ms: float,
            fallback_exc: Exception,
        ) -> None:
            self._emit_debug_diagnostic(
                "llm_http_attempt_failed",
                operation="complete_with_tools",
                call_mode="without_tools_fallback",
                attempt=attempt,
                attempts_total=total,
                elapsed_ms=round(elapsed_ms, 1),
                message_count=len(full_messages),
                tool_count=0,
                error_type=type(fallback_exc).__name__,
                error=str(fallback_exc),
            )
            self._schedule_transcript_record(
                direction="response",
                operation="complete_with_tools_without_tools_fallback_error",
                attempt=attempt,
                attempts_total=total,
                payload={"error_type": type(fallback_exc).__name__, "error": str(fallback_exc)},
                content_type="application/json",
                error_type=type(fallback_exc).__name__,
            )

        async def _call_with_tools() -> LLMResponseWithTools:
            kwargs: dict[str, Any] = {
                "model": self._deployment,
                "messages": full_messages,
                "tools": openai_tools,
                "tool_choice": "auto",
            }
            if resolved_temp is not None:
                kwargs["temperature"] = resolved_temp
            if resolved_max_tokens is not None:
                kwargs["max_completion_tokens"] = resolved_max_tokens
            if resolved_reasoning is not None:
                kwargs["reasoning_effort"] = resolved_reasoning
            if self._verbosity is not None:
                kwargs["verbosity"] = self._verbosity
            await self._write_transcript_record(
                direction="request",
                operation="complete_with_tools",
                attempt=current_attempt or None,
                attempts_total=attempts_total,
                payload=kwargs,
            )
            resp = await self._client.chat.completions.create(**kwargs)
            await self._write_transcript_record(
                direction="response",
                operation="complete_with_tools",
                attempt=current_attempt or None,
                attempts_total=attempts_total,
                payload=resp.model_dump(),
            )
            return self._parse_chat_completion(resp)

        async def _call_without_tools() -> LLMResponseWithTools:
            kwargs: dict[str, Any] = {
                "model": self._deployment,
                "messages": full_messages,
            }
            if resolved_temp is not None:
                kwargs["temperature"] = resolved_temp
            if resolved_max_tokens is not None:
                kwargs["max_completion_tokens"] = min(resolved_max_tokens, 1024)
            if resolved_reasoning is not None:
                kwargs["reasoning_effort"] = resolved_reasoning
            if self._verbosity is not None:
                kwargs["verbosity"] = self._verbosity
            await self._write_transcript_record(
                direction="request",
                operation="complete_with_tools_without_tools_fallback",
                attempt=current_attempt or None,
                attempts_total=1,
                payload=kwargs,
            )
            resp = await self._client.chat.completions.create(**kwargs)
            await self._write_transcript_record(
                direction="response",
                operation="complete_with_tools_without_tools_fallback",
                attempt=current_attempt or None,
                attempts_total=1,
                payload=resp.model_dump(),
            )
            parsed = self._parse_chat_completion(resp)
            # No tools were offered in fallback mode.
            return LLMResponseWithTools(
                content=parsed.content,
                tool_calls=[],
                stop_reason="end_turn",
                model=parsed.model,
                input_tokens=parsed.input_tokens,
                output_tokens=parsed.output_tokens,
                raw=parsed.raw,
            )

        try:
            return await llm_retry(
                _call_with_tools,
                attempts=self._retry_attempts,
                base_delay=self._retry_base_delay,
                on_attempt_start=_on_with_tools_attempt_start,
                on_attempt_success=_on_with_tools_attempt_success,
                on_attempt_error=_on_with_tools_attempt_error,
            )
        except RuntimeError as exc:
            # Some Azure deployments intermittently reject valid tool prompts with
            # 400 invalid_prompt/internal error. Degrade to text-only response so
            # the agent loop continues instead of crashing.
            if openai_tools and "invalid_prompt" in str(exc).lower():
                self._emit_debug_diagnostic(
                    "llm_http_attempt_failed",
                    operation="complete_with_tools",
                    call_mode="with_tools",
                    attempt=self._retry_attempts,
                    attempts_total=self._retry_attempts,
                    fallback="without_tools",
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                return await llm_retry(
                    _call_without_tools,
                    attempts=1,
                    base_delay=self._retry_base_delay,
                    on_attempt_start=_on_fallback_attempt_start,
                    on_attempt_success=_on_fallback_attempt_success,
                    on_attempt_error=_on_fallback_attempt_error,
                )
            raise

    # ── Message-builder helpers ───────────────────────────────────────────────

    @staticmethod
    def user_message(content: str) -> dict:
        return {"role": "user", "content": content}

    @staticmethod
    def assistant_message_with_tools(
        text: str | None,
        tool_calls: list[ToolCall],
    ) -> dict:
        openai_tool_calls = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments),
                },
            }
            for tc in tool_calls
        ]
        return {
            "role": "assistant",
            # Azure chat/completions can reject assistant turns with null content.
            # Keep a string payload for compatibility across API versions.
            "content": text or "",
            "tool_calls": openai_tool_calls,
        }

    @staticmethod
    def tool_result_message(tool_results: list) -> list[dict]:
        return [
            {
                "role": "tool",
                "tool_call_id": r.tool_call_id,
                "content": r.content if isinstance(r.content, str) else json.dumps(r.content, default=str),
            }
            for r in tool_results
        ]

    @staticmethod
    def _sanitize_message(message: dict[str, Any]) -> dict[str, Any]:
        """Normalize message content to Azure-compatible payload shapes."""
        m = dict(message)
        if "content" not in m:
            return m
        content = m.get("content")
        if content is None:
            m["content"] = ""
        elif not isinstance(content, (str, list)):
            m["content"] = json.dumps(content, default=str)
        return m

    @staticmethod
    def _parse_chat_completion(resp: Any) -> LLMResponseWithTools:
        choice = resp.choices[0]
        msg = choice.message

        tool_calls: list[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        stop_reason = choice.finish_reason or "end_turn"
        if stop_reason == "tool_calls":
            stop_reason = "tool_use"

        return LLMResponseWithTools(
            content=msg.content or None,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            model=resp.model,
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            output_tokens=resp.usage.completion_tokens if resp.usage else 0,
            raw=resp.model_dump(),
        )

