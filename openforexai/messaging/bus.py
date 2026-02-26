from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Awaitable, Callable

from openforexai.models.messaging import AgentMessage, EventType

Handler = Callable[[AgentMessage], Awaitable[None]]


class EventBus:
    """In-process async pub/sub bus backed by a single asyncio.Queue.

    Agents call ``publish()`` to emit events and ``subscribe()`` to register
    async handler coroutines.  The dispatch loop runs as a background task
    (``start_dispatch_loop()``) and fans out each message to all matching
    handlers concurrently via ``asyncio.gather``.
    """

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[Handler]] = defaultdict(list)
        self._queue: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self._running = False

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        """Register *handler* for *event_type*. Safe to call before start."""
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        try:
            self._subscribers[event_type].remove(handler)
        except ValueError:
            pass

    async def publish(self, message: AgentMessage) -> None:
        """Enqueue a message for async dispatch."""
        await self._queue.put(message)

    async def start_dispatch_loop(self) -> None:
        """Run as a dedicated asyncio Task; dispatches messages until stopped."""
        self._running = True
        while self._running:
            try:
                message = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            handlers = list(self._subscribers.get(message.event_type, []))
            if handlers:
                results = await asyncio.gather(
                    *[h(message) for h in handlers], return_exceptions=True
                )
                for r in results:
                    if isinstance(r, Exception):
                        import logging

                        logging.getLogger(__name__).exception(
                            "Handler error for event %s: %s", message.event_type, r
                        )
            self._queue.task_done()

    def stop(self) -> None:
        self._running = False
