"""RuntimeRegistry — stores live module instances for agent access.

Bootstrap creates LLM and broker instances once, registers them here.
Agents retrieve them by name after receiving their config via the EventBus.

Usage::

    # At bootstrap:
    RuntimeRegistry.register_llm("anthropic_claude", AnthropicLLMProvider(...))
    RuntimeRegistry.register_broker("oanda", OANDABroker(...))

    # In Agent after config received:
    llm    = RuntimeRegistry.get_llm("anthropic_claude")
    broker = RuntimeRegistry.get_broker("oanda")
"""
from __future__ import annotations

from openforexai.ports.broker import AbstractBroker
from openforexai.ports.llm import AbstractLLMProvider


class RuntimeRegistry:
    """Singleton-style registry for live module instances."""

    _llm:    dict[str, AbstractLLMProvider] = {}
    _broker: dict[str, AbstractBroker] = {}

    # ── LLM ──────────────────────────────────────────────────────────────────

    @classmethod
    def register_llm(cls, name: str, instance: AbstractLLMProvider) -> None:
        cls._llm[name] = instance

    @classmethod
    def get_llm(cls, name: str) -> AbstractLLMProvider:
        if name not in cls._llm:
            raise KeyError(
                f"LLM instance '{name}' not registered. "
                f"Registered: {list(cls._llm)}"
            )
        return cls._llm[name]

    @classmethod
    def list_llm(cls) -> list[str]:
        return list(cls._llm)

    # ── Broker ────────────────────────────────────────────────────────────────

    @classmethod
    def register_broker(cls, name: str, instance: AbstractBroker) -> None:
        cls._broker[name] = instance

    @classmethod
    def get_broker(cls, name: str) -> AbstractBroker:
        if name not in cls._broker:
            raise KeyError(
                f"Broker instance '{name}' not registered. "
                f"Registered: {list(cls._broker)}"
            )
        return cls._broker[name]

    @classmethod
    def list_brokers(cls) -> list[str]:
        return list(cls._broker)
