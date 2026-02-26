from __future__ import annotations

from openforexai.ports.broker import AbstractBroker
from openforexai.ports.database import AbstractRepository
from openforexai.ports.llm import AbstractLLMProvider


class PluginRegistry:
    """Central registry for all pluggable adapters.

    Adapters self-register at import time via their package ``__init__.py``::

        PluginRegistry.register_broker("oanda", OANDABroker)
    """

    _brokers: dict[str, type[AbstractBroker]] = {}
    _llm_providers: dict[str, type[AbstractLLMProvider]] = {}
    _repositories: dict[str, type[AbstractRepository]] = {}

    # ── Brokers ──────────────────────────────────────────────────────────────

    @classmethod
    def register_broker(cls, name: str, klass: type[AbstractBroker]) -> None:
        cls._brokers[name] = klass

    @classmethod
    def get_broker(cls, name: str) -> type[AbstractBroker]:
        if name not in cls._brokers:
            raise ValueError(
                f"Unknown broker '{name}'. Registered: {list(cls._brokers)}"
            )
        return cls._brokers[name]

    @classmethod
    def list_brokers(cls) -> list[str]:
        return list(cls._brokers)

    # ── LLM providers ────────────────────────────────────────────────────────

    @classmethod
    def register_llm_provider(cls, name: str, klass: type[AbstractLLMProvider]) -> None:
        cls._llm_providers[name] = klass

    @classmethod
    def get_llm_provider(cls, name: str) -> type[AbstractLLMProvider]:
        if name not in cls._llm_providers:
            raise ValueError(
                f"Unknown LLM provider '{name}'. Registered: {list(cls._llm_providers)}"
            )
        return cls._llm_providers[name]

    @classmethod
    def list_llm_providers(cls) -> list[str]:
        return list(cls._llm_providers)

    # ── Repositories ─────────────────────────────────────────────────────────

    @classmethod
    def register_repository(cls, name: str, klass: type[AbstractRepository]) -> None:
        cls._repositories[name] = klass

    @classmethod
    def get_repository(cls, name: str) -> type[AbstractRepository]:
        if name not in cls._repositories:
            raise ValueError(
                f"Unknown repository backend '{name}'. Registered: {list(cls._repositories)}"
            )
        return cls._repositories[name]

    @classmethod
    def list_repositories(cls) -> list[str]:
        return list(cls._repositories)
