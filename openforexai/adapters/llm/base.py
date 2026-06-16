from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any


async def llm_retry(
    coro_fn,
    attempts: int = 3,
    base_delay: float = 1.0,
    on_attempt_start=None,
    on_attempt_success=None,
    on_attempt_error=None,
) -> Any:
    """Retry an LLM call with exponential back-off on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        attempt_number = attempt + 1
        if on_attempt_start is not None:
            on_attempt_start(attempt_number, attempts)
        started = perf_counter()
        try:
            result = await coro_fn()
        except Exception as exc:
            last_exc = exc
            if on_attempt_error is not None:
                on_attempt_error(
                    attempt_number,
                    attempts,
                    (perf_counter() - started) * 1000.0,
                    exc,
                )
            if attempt < attempts - 1:
                await asyncio.sleep(base_delay * (2**attempt))
        else:
            if on_attempt_success is not None:
                on_attempt_success(
                    attempt_number,
                    attempts,
                    (perf_counter() - started) * 1000.0,
                )
            return result
    raise RuntimeError(
        f"LLM call failed after {attempts} attempts: {type(last_exc).__name__}: {last_exc}"
    ) from last_exc

