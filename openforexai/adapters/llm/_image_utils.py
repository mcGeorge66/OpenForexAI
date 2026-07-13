"""Shared utility: resolve image markers and file paths to base64 data URIs.

Markers are scanned from prompt text at the LLM adapter level — regardless of
where the prompt was assembled.  Two marker forms are supported:

    image[path]      embed image; file is kept after use
    imagetmp[path]   embed image; file is DELETED after the LLM call

Paths starting with ``/`` or ``\\`` are resolved relative to cwd (project root).
Already-encoded ``data:image/...;base64,...`` strings are passed through unchanged.
"""
from __future__ import annotations

import base64
import logging
import os
import re
from pathlib import Path

_log = logging.getLogger(__name__)

_IMAGE_SUFFIXES = frozenset({'.png', '.jpg', '.jpeg', '.gif', '.webp'})
_MEDIA_TYPES: dict[str, str] = {
    '.png':  'image/png',
    '.jpg':  'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif':  'image/gif',
    '.webp': 'image/webp',
}

# imagetmp must be checked before image so the longer prefix wins
_MARKER_RE = re.compile(r'imagetmp\[([^\]]+)\]|image\[([^\]]+)\]')


# ── Path resolution ────────────────────────────────────────────────────────────

def _resolve_path(raw: str) -> Path:
    """Resolve *raw* to an absolute Path.

    A leading ``/`` or ``\\`` means project-root-relative (cwd), not
    drive-root on Windows.
    """
    raw = raw.strip()
    if raw.startswith(('/', '\\')):
        return Path(os.getcwd()) / raw.lstrip('/\\')
    return Path(raw)


# ── Marker extraction ─────────────────────────────────────────────────────────

def _extract_markers(text: str) -> tuple[str, list[tuple[str, bool]]]:
    """Strip image markers from *text* and collect the paths they reference.

    Returns ``(cleaned_text, [(path, is_tmp), ...])``.
    """
    found: list[tuple[str, bool]] = []

    def _replace(m: re.Match) -> str:
        if m.group(1) is not None:          # imagetmp[...]
            found.append((m.group(1).strip(), True))
        else:                                # image[...]
            found.append((m.group(2).strip(), False))
        return ''

    cleaned = _MARKER_RE.sub(_replace, text).strip()
    return cleaned, found


def scan_prompts_for_images(
    system_prompt: str = '',
    messages: list[dict] | None = None,
    user_message: str | None = None,
) -> tuple[str, list[dict] | None, str | None, list[str], list[str]]:
    """Scan all text fields for ``image[]`` / ``imagetmp[]`` markers.

    Markers are stripped from every text field.  Collected paths are returned
    separately so the caller can resolve and inject them.

    Returns
    -------
    clean_system   : str
    clean_messages : list[dict] | None  (None when *messages* was None)
    clean_user     : str | None         (None when *user_message* was None)
    regular_paths  : list[str]          paths from image[] markers
    tmp_paths      : list[str]          paths from imagetmp[] markers (delete after use)
    """
    all_found: list[tuple[str, bool]] = []

    clean_system, found = _extract_markers(system_prompt or '')
    all_found.extend(found)

    clean_messages: list[dict] | None = None
    if messages is not None:
        clean_messages = []
        for msg in messages:
            content = msg.get('content', '')
            if isinstance(content, str):
                cleaned_content, found = _extract_markers(content)
                all_found.extend(found)
                clean_messages.append({**msg, 'content': cleaned_content})
            else:
                clean_messages.append(msg)

    clean_user: str | None = None
    if user_message is not None:
        clean_user, found = _extract_markers(user_message)
        all_found.extend(found)

    regular_paths = [p for p, is_tmp in all_found if not is_tmp]
    tmp_paths     = [p for p, is_tmp in all_found if is_tmp]
    return clean_system, clean_messages, clean_user, regular_paths, tmp_paths


# ── Resolution & cleanup ──────────────────────────────────────────────────────

def resolve_images(images: list[str] | None) -> list[str]:
    """Convert a list of file paths / data URIs to base64 data URIs.

    Already-encoded ``data:image/...`` URIs are passed through unchanged.
    File paths are read from disk and encoded.  Missing or unreadable files
    are logged at ERROR level and skipped (image will NOT be sent to LLM).
    """
    if not images:
        return []

    resolved: list[str] = []
    for raw in images:
        if not raw or not isinstance(raw, str):
            continue
        raw = raw.strip()
        if raw.startswith('data:image/'):
            resolved.append(raw)
            continue
        path = _resolve_path(raw)
        suffix = path.suffix.lower()
        if suffix not in _IMAGE_SUFFIXES:
            _log.warning("resolve_images: unsupported extension %r — skipping", suffix)
            continue
        if not path.exists():
            _log.error(
                "resolve_images: file not found %r (resolved to %s) — image will NOT be sent to LLM",
                raw, path,
            )
            continue
        try:
            data = path.read_bytes()
            media_type = _MEDIA_TYPES[suffix]
            b64 = base64.b64encode(data).decode('ascii')
            resolved.append(f'data:{media_type};base64,{b64}')
        except Exception as exc:
            _log.error(
                "resolve_images: could not load %r: %s — image will NOT be sent to LLM",
                raw, exc,
            )

    return resolved


def delete_tmp_images(paths: list[str]) -> None:
    """Delete temporary image files referenced by ``imagetmp[]`` markers."""
    for raw in paths:
        path = _resolve_path(raw)
        try:
            if path.exists():
                path.unlink()
                _log.info("resolve_images: deleted tmp image %s", path)
        except Exception as exc:
            _log.warning("resolve_images: could not delete tmp image %s: %s", path, exc)
