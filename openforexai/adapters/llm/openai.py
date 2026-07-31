from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import openai as _openai

from openforexai.adapters.llm._image_utils import (
    delete_tmp_images,
    resolve_images,
    scan_prompts_for_images,
)
from openforexai.adapters.llm.base import describe_exception, llm_retry
from openforexai.ports.llm import (
    AbstractLLMProvider,
    LLMResponse,
    LLMResponseWithTools,
    ToolCall,
    ToolSpec,
)


def _inject_images_openai(
    messages: list[dict[str, Any]],
    resolved: list[str],
) -> list[dict[str, Any]]:
    """Prepend image blocks to the last user message for OpenAI format."""
    if not resolved:
        return messages
    augmented = list(messages)
    for i in range(len(augmented) - 1, -1, -1):
        if augmented[i].get("role") == "user":
            text = augmented[i].get("content", "")
            content: list[dict[str, Any]] = [{"type": "text", "text": text if isinstance(text, str) else str(text)}]
            for img in resolved:
                content.append({"type": "image_url", "image_url": {"url": img, "detail": "high"}})
            augmented[i] = {**augmented[i], "content": content}
            break
    return augmented


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


class OpenAILLMProvider(AbstractLLMProvider):
    """OpenAI-compatible adapter — real OpenAI, Azure AI Foundry's v1 endpoint,
    LM Studio, and any other provider exposing the OpenAI Chat Completions API,
    all via the plain ``openai`` SDK client pointed at a ``base_url``. There is
    no Azure-specific adapter: Azure AI Foundry's v1 API is fully OpenAI-compatible
    (no ``api-version`` query param, no separate ``AzureOpenAI`` client needed) —
    point ``base_url`` at ``https://<resource>.services.ai.azure.com/openai/v1``
    and use the deployment name as ``model``.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str | None = None,
        retry_attempts: int = 3,
        retry_base_delay: float = 1.0,
        timeout_seconds: float = 30.0,
        sdk_max_retries: int = 0,
        default_temperature: float | None = None,
        default_max_tokens: int = 4096,
        reasoning_effort: str | None = None,
        verbosity: str | None = None,
        transcript_enabled: bool = False,
        transcript_path: str | None = None,
    ) -> None:
        self._model = model
        self._retry_attempts = retry_attempts
        self._retry_base_delay = retry_base_delay
        self._client = _openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=sdk_max_retries,
        )
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens
        self._reasoning_effort = reasoning_effort
        self._verbosity = verbosity
        self._transcript_enabled = bool(transcript_enabled)
        self._transcript_base_path = self._resolve_transcript_path(transcript_path)
        self._transcript_lock = asyncio.Lock()
        # Track the date last written so we can prune old files on rollover only
        self._transcript_last_date: str | None = None
        # Keep at most this many dated transcript files in the directory
        self._transcript_max_files = 10
        # Hold references to fire-and-forget transcript tasks so they can't be
        # silently garbage-collected before they run (and thus never written).
        self._background_tasks: set[asyncio.Task] = set()

    @classmethod
    def from_config(cls, cfg: dict) -> OpenAILLMProvider:
        reasoning_effort = cfg.get("reasoning_effort")
        if reasoning_effort is not None:
            if not isinstance(reasoning_effort, str):
                raise ValueError("LLM config key 'reasoning_effort' must be a string when provided.")
            allowed_efforts = {"none", "low", "medium", "high"}
            if reasoning_effort not in allowed_efforts:
                raise ValueError(
                    f"LLM config key 'reasoning_effort' must be one of {sorted(allowed_efforts)}, "
                    f"got {reasoning_effort!r}."
                )
        verbosity = cfg.get("verbosity")
        if verbosity is not None:
            if not isinstance(verbosity, str):
                raise ValueError("LLM config key 'verbosity' must be a string when provided.")
            allowed_verbosity = {"low", "medium", "high"}
            if verbosity not in allowed_verbosity:
                raise ValueError(
                    f"LLM config key 'verbosity' must be one of {sorted(allowed_verbosity)}, "
                    f"got {verbosity!r}."
                )
        transcript_enabled = bool(cfg.get("transcript_enabled", False))
        transcript_path = cfg.get("transcript_path")
        if transcript_enabled and not isinstance(transcript_path, str):
            raise ValueError("LLM config must define 'transcript_path' when 'transcript_enabled' is true.")
        return cls(
            api_key=cfg.get("api_key", ""),
            model=cfg.get("model", "gpt-4o"),
            base_url=cfg.get("base_url") or None,
            retry_attempts=cfg.get("retry_attempts", 3),
            retry_base_delay=cfg.get("retry_base_delay", 1.0),
            timeout_seconds=cfg.get("timeout_seconds", 30.0),
            sdk_max_retries=cfg.get("sdk_max_retries", 0),
            default_temperature=(
                cfg.get("temperature") if isinstance(cfg.get("temperature"), (int, float)) else None
            ),
            default_max_tokens=cfg.get("max_tokens", 4096),
            reasoning_effort=reasoning_effort,
            verbosity=verbosity,
            transcript_enabled=transcript_enabled,
            transcript_path=transcript_path,
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

    # ── Transcript logging (forensic record of every request/response) ────────

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
        payload: Any,
        content_type: str = "application/json",
        error_type: str | None = None,
    ) -> None:
        if not self._transcript_enabled or self._transcript_base_path is None:
            return

        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        sender = "openforexai" if direction == "request" else "llm_provider"
        receiver = "llm_provider" if direction == "request" else "openforexai"
        raw_payload = self._serialize_json_payload(payload)

        header_lines = [
            "=" * 120,
            f"timestamp: {timestamp}",
            f"sender: {sender}",
            f"receiver: {receiver}",
            f"direction: {direction}",
            f"operation: {operation}",
        ]
        if error_type:
            header_lines.append(f"error_type: {error_type}")
        header_lines.extend([
            f"model: {self._model}",
            f"content_type: {content_type}",
            "-" * 120,
            raw_payload,
            "",
        ])
        record = "\n".join(header_lines)

        async with self._transcript_lock:
            await asyncio.to_thread(self._append_transcript_text, record)

    def _schedule_transcript_record(self, **kwargs: Any) -> None:
        if not self._transcript_enabled or self._transcript_base_path is None:
            return
        task = asyncio.create_task(self._write_transcript_record(**kwargs))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _today_transcript_path(self) -> Path | None:
        """Return today's dated transcript file path.

        Base path 'logs/llm_transcript.log' becomes
        'logs/llm_transcript_YYYY-MM-DD.log' for today's UTC date.
        """
        base = self._transcript_base_path
        if base is None:
            return None
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        return base.with_name(f"{base.stem}_{date_str}{base.suffix}")

    def _prune_old_transcript_files(self) -> None:
        """Delete the oldest dated transcript files, keeping only the newest N."""
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
        images: list[str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        resolved_temp = self._default_temperature if temperature is None else temperature
        resolved_max_tokens = self._default_max_tokens if max_tokens is None else max_tokens
        resolved_reasoning = self._reasoning_effort if reasoning_effort is None else reasoning_effort

        clean_system, _, clean_user, regular_paths, tmp_paths = scan_prompts_for_images(
            system_prompt=system_prompt,
            user_message=user_message,
        )
        resolved_images = resolve_images(regular_paths + tmp_paths + list(images or []))

        async def _call() -> LLMResponse:
            if resolved_images:
                user_content: list[dict[str, Any]] = [{"type": "text", "text": clean_user}]
                for img in resolved_images:
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": img, "detail": "high"},
                    })
            else:
                user_content = clean_user  # type: ignore[assignment]

            kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": clean_system},
                    {"role": "user", "content": user_content},
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
            await self._write_transcript_record(direction="request", operation="complete", payload=kwargs)
            resp = await self._client.chat.completions.create(**kwargs)
            await self._write_transcript_record(
                direction="response", operation="complete", payload=resp.model_dump(),
            )
            choice = resp.choices[0]
            return LLMResponse(
                content=choice.message.content or "",
                model=resp.model,
                input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
                output_tokens=resp.usage.completion_tokens if resp.usage else 0,
                raw=resp.model_dump(),
            )

        def _on_complete_attempt_error(attempt: int, total: int, elapsed_ms: float, exc: Exception) -> None:
            detail = describe_exception(exc)
            self._schedule_transcript_record(
                direction="response",
                operation="complete_error",
                payload=detail,
                error_type=detail["error_type"],
            )

        try:
            return await llm_retry(
                _call,
                attempts=self._retry_attempts,
                base_delay=self._retry_base_delay,
                on_attempt_error=_on_complete_attempt_error,
            )
        finally:
            delete_tmp_images(tmp_paths)

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
        images: list[str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
    ) -> LLMResponseWithTools:
        """Single turn using the OpenAI-compatible native function-calling API."""
        clean_system, clean_messages, _, regular_paths, tmp_paths = scan_prompts_for_images(
            system_prompt=system_prompt,
            messages=messages,
        )
        openai_tools = [_to_openai_tool(t) for t in tools]
        effective_messages = _inject_images_openai(
            clean_messages, resolve_images(regular_paths + tmp_paths + list(images or []))
        )
        # Convert the canonical Anthropic-style messages (tool_use/tool_result
        # content blocks) the agent builds into OpenAI's tool_calls/tool-role
        # shape — without this, any turn after the first tool call gets sent in
        # a format the API rejects with a 400.
        full_messages = [{"role": "system", "content": clean_system}] + \
            self._sanitize_messages(effective_messages)

        resolved_temp = self._default_temperature if temperature is None else temperature
        resolved_max_tokens = self._default_max_tokens if max_tokens is None else max_tokens
        resolved_reasoning = self._reasoning_effort if reasoning_effort is None else reasoning_effort

        async def _call() -> LLMResponseWithTools:
            kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": full_messages,
            }
            # OpenAI-family APIs reject tools=[] with tool_choice="auto" outright —
            # only send them when there's actually something to offer.
            if openai_tools:
                kwargs["tools"] = openai_tools
                kwargs["tool_choice"] = "auto"
            if resolved_temp is not None:
                kwargs["temperature"] = resolved_temp
            if resolved_max_tokens is not None:
                kwargs["max_completion_tokens"] = resolved_max_tokens
            # Some providers (confirmed: Azure AI Foundry v1, GPT-5 family) reject
            # function tools combined with reasoning_effort on /chat/completions
            # outright ("...are not supported... Please use /v1/responses
            # instead."). Tools are core to the agent loop, reasoning_effort is a
            # quality knob — drop the knob rather than the endpoint every
            # OpenAI-compatible provider (incl. local ones) actually implements.
            if resolved_reasoning is not None and not openai_tools:
                kwargs["reasoning_effort"] = resolved_reasoning
            if self._verbosity is not None:
                kwargs["verbosity"] = self._verbosity
            await self._write_transcript_record(direction="request", operation="complete_with_tools", payload=kwargs)
            resp = await self._client.chat.completions.create(**kwargs)
            await self._write_transcript_record(
                direction="response", operation="complete_with_tools", payload=resp.model_dump(),
            )
            return self._parse_chat_completion(resp)

        def _on_attempt_error(attempt: int, total: int, elapsed_ms: float, exc: Exception) -> None:
            detail = describe_exception(exc)
            self._schedule_transcript_record(
                direction="response",
                operation="complete_with_tools_error",
                payload=detail,
                error_type=detail["error_type"],
            )

        try:
            return await llm_retry(
                _call,
                attempts=self._retry_attempts,
                base_delay=self._retry_base_delay,
                on_attempt_error=_on_attempt_error,
            )
        finally:
            delete_tmp_images(tmp_paths)

    # ── Message-builder helpers ───────────────────────────────────────────────

    @staticmethod
    def user_message(content: str) -> dict:
        return {"role": "user", "content": content}

    @staticmethod
    def assistant_message_with_tools(
        text: str | None,
        tool_calls: list[ToolCall],
    ) -> dict:
        """Build the assistant turn to append after a tool-use response."""
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
            "content": text,
            "tool_calls": openai_tool_calls,
        }

    @staticmethod
    def tool_result_message(tool_results: list) -> list[dict]:
        """Build tool-result turns (OpenAI uses one message per result)."""
        return [
            {
                "role": "tool",
                "tool_call_id": r.tool_call_id,
                "content": r.content if isinstance(r.content, str) else json.dumps(r.content, default=str),
            }
            for r in tool_results
        ]

    @staticmethod
    def _convert_message(message: dict[str, Any]) -> list[dict[str, Any]]:
        """Convert one canonical (Anthropic-style) message to 1-N OpenAI messages.

        The agent builds conversation history in canonical format::

            # assistant turn with tool call
            {"role": "assistant", "content": [
                {"type": "text",     "text": "..."},
                {"type": "tool_use", "id": "...", "name": "...", "input": {...}},
            ]}

            # tool result turn
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "...", "content": "...", "is_error": False},
            ]}

        OpenAI expects::

            {"role": "assistant", "content": "...", "tool_calls": [
                {"id": "...", "type": "function", "function": {"name": "...", "arguments": "..."}},
            ]}
            {"role": "tool", "tool_call_id": "...", "content": "..."}
        """
        role = message.get("role", "user")
        content = message.get("content")

        # ── Anthropic assistant turn ──────────────────────────────────────────
        if role == "assistant" and isinstance(content, list):
            text_blocks = [b.get("text", "") for b in content if b.get("type") == "text"]
            tool_uses   = [b for b in content if b.get("type") == "tool_use"]
            if tool_uses:
                return [{
                    "role": "assistant",
                    "content": "".join(text_blocks),
                    "tool_calls": [
                        {
                            "id": tu["id"],
                            "type": "function",
                            "function": {
                                "name": tu["name"],
                                "arguments": json.dumps(tu.get("input", {})),
                            },
                        }
                        for tu in tool_uses
                    ],
                }]
            # Pure text blocks in a list — flatten to string
            return [{"role": "assistant", "content": "".join(text_blocks)}]

        # ── Anthropic tool-result turn ────────────────────────────────────────
        if role == "user" and isinstance(content, list):
            tool_results = [b for b in content if b.get("type") == "tool_result"]
            if tool_results:
                return [
                    {
                        "role": "tool",
                        "tool_call_id": tr["tool_use_id"],
                        "content": (
                            tr["content"]
                            if isinstance(tr["content"], str)
                            else json.dumps(tr["content"], default=str)
                        ),
                    }
                    for tr in tool_results
                ]

        # ── Regular message — normalize content ───────────────────────────────
        m = dict(message)
        if content is None:
            m["content"] = ""
        elif not isinstance(content, (str, list)):
            m["content"] = json.dumps(content, default=str)
        return [m]

    @classmethod
    def _sanitize_messages(cls, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert a list of canonical messages to OpenAI format."""
        result: list[dict[str, Any]] = []
        for msg in messages:
            result.extend(cls._convert_message(msg))
        return result

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
        elif stop_reason == "length":
            stop_reason = "max_tokens"

        return LLMResponseWithTools(
            content=msg.content or None,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            model=resp.model,
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            output_tokens=resp.usage.completion_tokens if resp.usage else 0,
            raw=resp.model_dump(),
        )
