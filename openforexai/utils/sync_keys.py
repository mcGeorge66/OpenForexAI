from __future__ import annotations

import secrets


def generate_sync_key(length: int = 16) -> str:
    """Return a short uppercase hex key suitable for broker comments."""
    if length < 8:
        length = 8
    return secrets.token_hex((length + 1) // 2).upper()[:length]
