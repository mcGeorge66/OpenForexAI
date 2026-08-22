# UI Patterns — named, reusable

Catalog of UI patterns built for one dialog that are candidates for reuse elsewhere.
Reference a pattern by name (e.g. "bau die Capped Scroll Box auch in [Dialog] ein")
instead of re-describing it each time.

---

## Capped Scroll Box

**Status:** Implemented in two places (see "Where implemented" below), each its own
copy of the same small component — not yet extracted into one shared component.

**What it does:** An LLM/assistant answer bubble that defaults to a fixed max height
(currently `16rem`, tuned to ~15 lines). The full text is always in the DOM — never
truncated — so when it overflows the capped height, a vertical scrollbar appears on
the right as a way to read the rest without leaving the collapsed state. A "Show more
(N lines)" button is also available to remove the height cap entirely (full,
unbounded view); "Show less" re-applies the cap. A "Copy" button is always present
next to it.

**Where implemented:**
- `ui/src/components/views/action/OrderInvestigateModal.tsx` — `AssistantMessageBubble`
  component (Orderbook "Ask AI" window). Constants: `COLLAPSED_MAX_LINES` (line-count
  threshold for showing the cap/button at all), `CAPPED_BOX_MAX_HEIGHT` (the CSS max
  height while capped).
- `ui/src/components/charts/ChartAssistantPanel.tsx` — `ChartAssistantMessageBubble`
  component (Chart Analysis's Chart Assistant window). Same two constants, same
  behavior; only applied to assistant messages, not the user's own (short) messages,
  matching OrderInvestigateModal.

**Not yet applied to** (would need the same treatment if requested):
- `ui/src/components/common/MessageBubble.tsx` — shared by the Entity/Script/Prompt
  assistant panels (EventComposer wizard, ScriptEditor fullscreen view, Agent Config
  wizard). Currently renders full content with no height cap at all.
