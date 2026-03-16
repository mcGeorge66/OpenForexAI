from __future__ import annotations

import asyncio

# True when runtime processing is paused.
_paused: bool = False


def is_paused() -> bool:
    return _paused


def pause() -> None:
    global _paused
    _paused = True


def resume() -> None:
    global _paused
    _paused = False


async def wait_until_resumed(poll_interval: float = 0.3) -> None:
    while _paused:
        await asyncio.sleep(poll_interval)
