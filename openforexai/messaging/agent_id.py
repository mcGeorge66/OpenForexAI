"""Agent ID parsing, formatting, and wildcard matching.

Format (mandatory):
    [BROKER(5)]-[PAIR(6)]-[TYPE(2)]-[NAME(1-5)]

Optional 5th segment (only when NAME is exactly 5 characters):
    [BROKER(5)]-[PAIR(6)]-[TYPE(2)]-[NAME(5)]-[EXT(any)]

Segment rules
-------------
BROKER  5 chars, padded right with '_' (e.g. 'OANDA', 'MT5__', 'GLOBL')
PAIR    6 chars, padded right with '_' (e.g. 'EURUSD', 'ALL___')
TYPE    2 chars exactly: 'AA' | 'BA' | 'GA' | 'AD'
NAME    1-5 chars (no padding at rest; stored as-is up to 5 chars)
EXT     optional, any length, only present when NAME == 5 chars exactly

Wildcards  ('*')
--------------
The ``matches(pattern)`` method supports '*' as a wildcard at any position
in any segment, e.g. 'OANDA-*-AA-*' or '*-EURUSD-*-*'.
'*' in a segment matches *any* segment value, including the full value with
padding characters.

Examples
--------
>>> aid = AgentId.parse("OANDA-EURUSD-AA-TRD1")
>>> aid.broker, aid.pair, aid.type, aid.name
('OANDA', 'EURUSD', 'AA', 'TRD1')
>>> aid.format()
'OANDA-EURUSD-AA-TRD1'

>>> aid2 = AgentId.parse("GLOBL-ALL___-GA-OPTIM-V2")
>>> aid2.extension
'V2'

>>> AgentId.parse("OANDA-EURUSD-AA-TRD1").matches("OANDA-*-AA-*")
True
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_VALID_TYPES = {"AA", "BA", "GA", "AD"}

# Pre-compiled pattern for full ID validation (no wildcards)
_ID_RE = re.compile(
    r"^([A-Z0-9_]{5})-([A-Z0-9_]{6})-([A-Z]{2})-([A-Z0-9]{1,5})(?:-(.+))?$"
)

# Wildcard pattern — same as above but every segment may be '*'
_WILD_RE = re.compile(
    r"^([A-Z0-9_*]{1,5})-([A-Z0-9_*]{1,6})-([A-Z*]{1,2})-([A-Z0-9*]{1,5})(?:-(.+))?$"
)


@dataclass(frozen=True)
class AgentId:
    """Parsed representation of a structured agent identifier."""

    broker: str      # 5 chars (may contain '_')
    pair: str        # 6 chars (may contain '_')
    type: str        # 2 chars: AA | BA | GA | AD
    name: str        # 1–5 chars
    extension: str | None = field(default=None)

    # ── Construction helpers ──────────────────────────────────────────────────

    @classmethod
    def parse(cls, raw: str) -> AgentId:
        """Parse a raw agent ID string.

        Raises ``ValueError`` if the format is invalid.
        """
        raw = raw.strip()
        m = _ID_RE.match(raw)
        if not m:
            raise ValueError(
                f"Invalid agent ID format: {raw!r}. "
                "Expected [BROKER(5)]-[PAIR(6)]-[TYPE(2)]-[NAME(1-5)] "
                "with optional -EXT when NAME is exactly 5 chars."
            )
        broker, pair, type_, name, ext = m.groups()
        if type_ not in _VALID_TYPES:
            raise ValueError(
                f"Invalid agent type {type_!r} in {raw!r}. "
                f"Must be one of: {', '.join(sorted(_VALID_TYPES))}"
            )
        if ext is not None and len(name) != 5:
            raise ValueError(
                f"5th segment (extension) is only allowed when NAME is "
                f"exactly 5 characters, got NAME={name!r} (len={len(name)}) in {raw!r}."
            )
        return cls(broker=broker, pair=pair, type=type_, name=name, extension=ext)

    @classmethod
    def try_parse(cls, raw: str) -> AgentId | None:
        """Like ``parse`` but returns ``None`` instead of raising."""
        try:
            return cls.parse(raw)
        except ValueError:
            return None

    @classmethod
    def build(
        cls,
        broker: str,
        pair: str,
        agent_type: str,
        name: str,
        extension: str | None = None,
    ) -> AgentId:
        """Build an AgentId with automatic padding.

        ``broker`` is right-padded with '_' to 5 chars.
        ``pair`` is right-padded with '_' to 6 chars.
        """
        broker = broker.upper().ljust(5, "_")[:5]
        pair = pair.upper().ljust(6, "_")[:6]
        agent_type = agent_type.upper()
        name = name.upper()[:5]
        if extension is not None and len(name) != 5:
            raise ValueError(
                "Extension is only allowed when name is exactly 5 characters."
            )
        return cls(
            broker=broker,
            pair=pair,
            type=agent_type,
            name=name,
            extension=extension,
        )

    # ── Formatting ────────────────────────────────────────────────────────────

    def format(self) -> str:
        """Return the canonical string representation."""
        base = f"{self.broker}-{self.pair}-{self.type}-{self.name}"
        if self.extension:
            return f"{base}-{self.extension}"
        return base

    def __str__(self) -> str:
        return self.format()

    # ── Wildcard matching ─────────────────────────────────────────────────────

    def matches(self, pattern: str) -> bool:
        """Return True if this ID matches *pattern*.

        Each segment in *pattern* may be '*' to match any value in the
        corresponding segment of this ID.  Segments are compared
        case-insensitively after stripping trailing '_' from both sides.

        Examples::

            AgentId.parse("OANDA-EURUSD-AA-TRD1").matches("OANDA-*-AA-*")   # True
            AgentId.parse("OANDA-EURUSD-AA-TRD1").matches("*-*-*-*")        # True
            AgentId.parse("OANDA-EURUSD-AA-TRD1").matches("MT5__-*-AA-*")   # False
        """
        return _pattern_matches(pattern, self)

    @classmethod
    def pattern_matches_id(cls, pattern: str, raw_id: str) -> bool:
        """Convenience: match *pattern* against *raw_id* without full parse."""
        aid = cls.try_parse(raw_id)
        if aid is None:
            return False
        return aid.matches(pattern)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _seg_match(pattern_seg: str, value_seg: str) -> bool:
    """Return True if *pattern_seg* matches *value_seg*.

    Supports '*' (entire segment wildcard) and leading/trailing '*' globs.
    Comparison is case-insensitive; trailing '_' padding is stripped first.
    """
    p = pattern_seg.upper().rstrip("_")
    v = value_seg.upper().rstrip("_")
    if p == "*":
        return True
    # Translate simple glob '*' prefix/suffix to regex
    if "*" in p:
        regex = "^" + re.escape(p).replace(r"\*", ".*") + "$"
        return bool(re.match(regex, v))
    return p == v


def _pattern_matches(pattern: str, aid: AgentId) -> bool:
    parts = pattern.strip().split("-", 4)
    segments = [aid.broker, aid.pair, aid.type, aid.name]
    # Must have at least 4 parts
    if len(parts) < 4:
        return False
    for i, seg in enumerate(segments):
        if not _seg_match(parts[i], seg):
            return False
    # Handle optional extension segment
    if len(parts) == 5:
        ext_val = aid.extension or ""
        if parts[4] != "*" and parts[4].upper() != ext_val.upper():
            return False
    return True


# ── Template substitution ─────────────────────────────────────────────────────

def substitute_template(template: str, sender: AgentId) -> str:
    """Replace ``{sender.*}`` placeholders in *template* with sender ID parts.

    Supported placeholders::

        {sender.broker}     → sender.broker  (5 chars, with underscores)
        {sender.pair}       → sender.pair    (6 chars, with underscores)
        {sender.type}       → sender.type    (2 chars)
        {sender.name}       → sender.name
        {sender.extension}  → sender.extension or ''
        {sender.id}         → full formatted sender ID

    All other text in *template* is kept as-is.
    """
    replacements = {
        "{sender.broker}": sender.broker,
        "{sender.pair}": sender.pair,
        "{sender.type}": sender.type,
        "{sender.name}": sender.name,
        "{sender.extension}": sender.extension or "",
        "{sender.id}": sender.format(),
    }
    result = template
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)
    return result


