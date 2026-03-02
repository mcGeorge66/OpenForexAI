from __future__ import annotations

import asyncio
from typing import Any


async def llm_retry(coro_fn, attempts: int = 3, base_delay: float = 1.0) -> Any:
    """Retry an LLM call with exponential back-off on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return await coro_fn()
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1:
                await asyncio.sleep(base_delay * (2**attempt))
    raise RuntimeError(
        f"LLM call failed after {attempts} attempts: {type(last_exc).__name__}: {last_exc}"
    ) from last_exc
