from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from openforexai.messaging.bus import EventBus
from openforexai.models.messaging import AgentMessage
from openforexai.ports.database import AbstractRepository
from openforexai.ports.llm import AbstractLLMProvider
from openforexai.utils.logging import get_logger


class BaseAgent(ABC):
    """Lifecycle-aware async agent base.

    Every agent:
    - Has a stable ``agent_id``
    - Holds references to an LLM provider, repository, and event bus
    - Supports a hot-swappable ``_system_prompt`` (used by OptimizationAgent)
    - Implements ``run_cycle()`` for its periodic or reactive logic
    """

    def __init__(
        self,
        agent_id: str,
        llm: AbstractLLMProvider,
        repository: AbstractRepository,
        bus: EventBus,
    ) -> None:
        self.agent_id = agent_id
        self.llm = llm
        self.repository = repository
        self.bus = bus
        self._system_prompt: str = ""
        self._running = False
        self._logger = get_logger(self.__class__.__name__).bind(agent_id=agent_id)

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the agent's async run loop."""
        self._running = True
        await self._on_start()
        try:
            while self._running:
                try:
                    await self.run_cycle()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._logger.exception("Unhandled error in run_cycle", error=str(exc))
        finally:
            await self._on_stop()

    async def stop(self) -> None:
        self._running = False

    async def _on_start(self) -> None:
        """Override for one-time initialisation at agent startup."""

    async def _on_stop(self) -> None:
        """Override for cleanup at agent shutdown."""

    @abstractmethod
    async def run_cycle(self) -> None:
        """One iteration of the agent's decision or reaction logic."""

    # ── Prompt hot-swap ──────────────────────────────────────────────────────

    def load_prompt(self, prompt: str) -> None:
        """Replace the active system prompt without stopping the agent."""
        self._system_prompt = prompt
        self._logger.info("System prompt updated", chars=len(prompt))

    # ── Bus helpers ──────────────────────────────────────────────────────────

    async def publish(self, message: AgentMessage) -> None:
        await self.bus.publish(message)
