from __future__ import annotations

import asyncio
import traceback as _traceback
from time import perf_counter
from typing import Any


def describe_exception(exc: BaseException) -> dict[str, Any]:
    """Extract diagnostic detail from an exception, including its cause chain.

    SDK-level exceptions (e.g. ``openai.APIConnectionError``) wrap the real
    transport failure (DNS/TLS/socket error) in ``__cause__`` behind a generic
    top-level message such as "Connection error.". Surfacing the cause here
    means failures can be diagnosed from the logs directly instead of only by
    reproducing with debug logging enabled.
    """
    cause = exc.__cause__
    return {
        "error_type": type(exc).__name__,
        "error": str(exc),
        "cause_type": type(cause).__name__ if cause is not None else None,
        "cause": str(cause) if cause is not None else None,
        "traceback": "".join(_traceback.format_exception(type(exc), exc, exc.__traceback__)),
    }


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
    detail = describe_exception(last_exc) if last_exc is not None else {}
    cause_suffix = (
        f" | cause: {detail['cause_type']}: {detail['cause']}"
        if detail.get("cause_type")
        else ""
    )
    raise RuntimeError(
        f"LLM call failed after {attempts} attempts: "
        f"{type(last_exc).__name__}: {last_exc}{cause_suffix}"
    ) from last_exc

