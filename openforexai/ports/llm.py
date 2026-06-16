"""LLM provider port — abstract interface for all LLM adapters.

Tool-calling protocol
---------------------
``complete_with_tools()`` implements the native tool_use loop contract:

1. Caller assembles ``messages`` (list of role/content dicts) and passes
   ``tools`` (list of ToolSpec dicts in canonical internal format).
2. Provider returns ``LLMResponseWithTools``.
3. If ``stop_reason == "tool_use"`` the caller executes the requested tools
   and appends assistant + tool-result turns to ``messages``.
4. Caller calls ``complete_with_tools()`` again with the extended messages.
5. Repeat until ``stop_reason == "end_turn"`` or loop limit reached.

Canonical ToolSpec format (Anthropic-style, adapter converts as needed)::

    {
        "name":        "calculate_indicator",
        "description": "Compute a technical indicator for a currency pair.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator": {"type": "string", "description": "e.g. RSI"},
                "period":    {"type": "integer"},
                "pair":      {"type": "string"}
            },
            "required": ["indicator", "period", "pair"]
        }
    }
"""
from __future__ import annotations

import functools
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# ── Prompt comment stripping ──────────────────────────────────────────────────

_COMMENT_RE = re.compile(r'\{#.*?#\}', re.DOTALL)

def _strip_prompt_comments(text: str) -> str:
    """Remove {# ... #} comments from a prompt before it reaches the LLM."""
    return _COMMENT_RE.sub('', text).strip()

def _strip_messages_comments(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip {# ... #} comments from all text content in a messages list."""
    result = []
    for msg in messages:
        content = msg.get('content')
        if isinstance(content, str):
            msg = {**msg, 'content': _strip_prompt_comments(content)}
        elif isinstance(content, list):
            new_blocks = []
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'text':
                    block = {**block, 'text': _strip_prompt_comments(block['text'])}
                new_blocks.append(block)
            msg = {**msg, 'content': new_blocks}
        result.append(msg)
    return result

# ── Shared data classes ───────────────────────────────────────────────────────

@dataclass
class LLMResponse:
    """Response from a plain (non-tool) completion."""
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    raw: dict[str, Any]


@dataclass
class ToolCall:
    """A single tool invocation requested by the LLM."""
    id: str                      # provider-assigned unique call ID
    name: str                    # tool name (matches ToolSpec["name"])
    arguments: dict[str, Any]    # parsed JSON arguments


@dataclass
class ToolResult:
    """The result of executing a ToolCall, returned to the LLM."""
    tool_call_id: str            # matches ToolCall.id
    name: str                    # tool name (echo)
    content: str                 # JSON-serialised result or error description
    is_error: bool = False


@dataclass
class LLMResponseWithTools:
    """Response from a tool-capable completion."""
    content: str | None                    # text content (may be None/empty when tool_calls present)
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"          # "end_turn" | "tool_use" | "stop" | "max_tokens"
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def wants_tools(self) -> bool:
        """True when the LLM wants to call one or more tools."""
        return self.stop_reason == "tool_use" and bool(self.tool_calls)


# ── Tool spec type alias (canonical internal format) ──────────────────────────
ToolSpec = dict[str, Any]


# ── Abstract provider ─────────────────────────────────────────────────────────

class AbstractLLMProvider(ABC):
    """Port: every LLM adapter must implement this contract."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for _method in ('complete', 'complete_structured', 'complete_with_tools'):
            if _method in cls.__dict__:
                _original = cls.__dict__[_method]
                _is_tool_method = _method == 'complete_with_tools'

                @functools.wraps(_original)
                async def _wrapper(
                    self: Any,
                    system_prompt: str,
                    *args: Any,
                    _fn: Any = _original,
                    _tool_method: bool = _is_tool_method,
                    **kwargs: Any,
                ) -> Any:
                    clean_system = _strip_prompt_comments(system_prompt)
                    if args:
                        if _tool_method:
                            args = (_strip_messages_comments(args[0]),) + args[1:]
                        else:
                            args = (_strip_prompt_comments(args[0]),) + args[1:]
                    if _tool_method and 'messages' in kwargs:
                        kwargs['messages'] = _strip_messages_comments(kwargs['messages'])
                    elif not _tool_method and 'user_message' in kwargs:
                        kwargs['user_message'] = _strip_prompt_comments(kwargs['user_message'])
                    return await _fn(self, clean_system, *args, **kwargs)

                setattr(cls, _method, _wrapper)

    @classmethod
    @abstractmethod
    def from_config(cls, cfg: dict[str, Any]) -> AbstractLLMProvider:
        """Instantiate the adapter from a module config dict.

        Each adapter reads the fields it needs from *cfg* — no caller-side
        branching required.  This is the only sanctioned way to create an
        LLM adapter instance outside of unit tests.
        """
        ...

    # ── Simple completions ────────────────────────────────────────────────────

    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
    ) -> LLMResponse: ...

    @abstractmethod
    async def complete_structured(
        self,
        system_prompt: str,
        user_message: str,
        response_schema: type,  # Pydantic model class
    ) -> dict[str, Any]: ...

    # ── Tool-use completions ──────────────────────────────────────────────────

    @abstractmethod
    async def complete_with_tools(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
    ) -> LLMResponseWithTools:
        """Single turn of a tool-use conversation.

        Args:
            system_prompt:  Static system instructions (role, constraints …).
            messages:       Conversation history.  Each element is a dict with
                            at minimum ``{"role": "user" | "assistant", "content": ...}``.
                            After a tool call the caller appends the assistant
                            turn and the tool-result turn before calling again.
            tools:          Tool definitions in canonical ToolSpec format.
            temperature:    Sampling temperature.
            max_tokens:     Maximum output tokens for this turn.

        Returns:
            ``LLMResponseWithTools`` — inspect ``.wants_tools`` to determine
            whether the loop should continue.
        """
        ...

    @property
    @abstractmethod
    def model_id(self) -> str: ...

    def set_debug_diagnostics(
        self,
        callback=None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Optional hook for request-scoped debug diagnostics.

        Providers may override this to emit request-attempt timing information
        back to the caller while the runtime is in DEBUG mode.
        """
        return None

