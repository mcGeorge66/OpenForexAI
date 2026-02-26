from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def async_retry(
    attempts: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """Decorator: retry an async function up to *attempts* times with exponential back-off."""

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(attempts):
                try:
                    return await fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < attempts - 1:
                        delay = base_delay * (2**attempt)
                        await asyncio.sleep(delay)
            raise RuntimeError(
                f"{fn.__qualname__} failed after {attempts} attempts"
            ) from last_exc

        return wrapper  # type: ignore[return-value]

    return decorator
