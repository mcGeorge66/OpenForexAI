"""Uvicorn-based async server wrapper for the Management API.

The server runs as a background asyncio Task alongside all agents.  It does
NOT block the main event loop.

Usage (from bootstrap.py)::

    server = ManagementServer(
        bus=event_bus,
        routing_table=routing_table,
        tool_registry=tool_registry,
        indicator_registry=indicator_registry,
        host="127.0.0.1",
        port=8765,
    )
    asyncio.create_task(server.serve())

To stop gracefully::

    await server.shutdown()
"""
from __future__ import annotations

import asyncio
import logging

_log = logging.getLogger(__name__)


class ManagementServer:
    """Wraps the FastAPI app in a non-blocking uvicorn server task.

    The server listens on localhost only by default (not exposed externally).
    """

    def __init__(
        self,
        bus=None,
        routing_table=None,
        tool_registry=None,
        indicator_registry=None,
        monitoring_bus=None,
        host: str = "127.0.0.1",
        port: int = 8765,
        log_level: str = "warning",
    ) -> None:
        self._host = host
        self._port = port
        self._log_level = log_level
        self._bus = bus
        self._routing_table = routing_table
        self._tool_registry = tool_registry
        self._indicator_registry = indicator_registry
        self._monitoring_bus = monitoring_bus
        self._server = None

    async def serve(self) -> None:
        """Start the HTTP server and run until ``shutdown()`` is called."""
        try:
            import uvicorn
        except ImportError:
            _log.error(
                "uvicorn is not installed — Management API unavailable. "
                "Install it with: pip install uvicorn[standard]"
            )
            return

        from openforexai.management.api import build_app

        app = build_app(
            bus=self._bus,
            routing_table=self._routing_table,
            tool_registry=self._tool_registry,
            indicator_registry=self._indicator_registry,
            monitoring_bus=self._monitoring_bus,
        )

        config = uvicorn.Config(
            app=app,
            host=self._host,
            port=self._port,
            log_level=self._log_level,
            loop="none",         # use the already-running asyncio loop
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        _log.info(
            "Management API starting on http://%s:%d", self._host, self._port
        )
        try:
            await self._server.serve()
        except asyncio.CancelledError:
            _log.info("Management API server task cancelled")
        except Exception as exc:
            _log.exception("Management API server error: %s", exc)

    async def shutdown(self) -> None:
        """Gracefully shut down the HTTP server."""
        if self._server is not None:
            self._server.should_exit = True
