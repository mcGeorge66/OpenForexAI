from __future__ import annotations

from datetime import UTC, datetime

from openforexai.models.optimization import PromptCandidate, TradePattern
from openforexai.ports.llm import AbstractLLMProvider

_EVOLVER_SYSTEM_PROMPT = """\
You are a prompt engineering expert for AI-based forex trading agents.
You will receive:
1. The current active system prompt for a trading agent.
2. A list of detected trade patterns (strengths and weaknesses).

Your task: generate an improved system prompt that capitalises on observed
strengths and mitigates weaknesses.  The new prompt must:
- Retain core trading principles (R/R ratio, stop-loss discipline, session awareness).
- Incorporate pattern-specific instructions (e.g. "avoid BUY signals during Tokyo session").
- Be concise and directive — no more than 400 words.

Respond ONLY with the new system prompt text, no explanations or markdown.
"""


async def evolve_prompt(
    current_prompt: str,
    patterns: list[TradePattern],
    pair: str,
    llm: AbstractLLMProvider,
    current_version: int,
) -> PromptCandidate:
    pattern_summary = "\n".join(
        f"- [{p.pattern_type}] {p.description}  "
        f"win_rate={p.win_rate_when_present:.2f}  avg_pnl={p.avg_pnl_when_present:.2f}"
        for p in patterns
    )
    user_message = (
        f"Current prompt:\n{current_prompt}\n\n"
        f"Detected patterns for {pair}:\n{pattern_summary}\n\n"
        "Generate an improved prompt."
    )
    response = await llm.complete(
        system_prompt=_EVOLVER_SYSTEM_PROMPT,
        user_message=user_message,
        temperature=0.3,
        max_tokens=600,
    )
    return PromptCandidate(
        pair=pair,
        version=current_version + 1,
        system_prompt=response.content.strip(),
        rationale=f"Evolved from v{current_version} based on {len(patterns)} patterns",
        source_patterns=[str(p.id) for p in patterns],
        is_active=False,
        created_at=datetime.now(UTC),
    )

