[Back to Action](ui.action.en.md)

# Prompt Workbench (PWB) — Handbook

The **Prompt Workbench** (abbreviated **PWB**) is where you **develop, refine, and test** an agent's system prompt against real historical data, without touching the live system or a real broker. Chat, Step, and Run all run through a detached agent that reuses the exact same LLM/tool-use loop as the real trading agents (`Agent._run_with_tools`) — what works here works the same way in production.

## What Is It Good For?

Typical situations where you'd reach for the PWB instead of a live agent:

- **Developing a new prompt** before assigning it to a real agent — e.g. "I want an agent that trades in a specific, well-known style" (see the worked example below).
- **Understanding why a live agent reached a particular conclusion** — load the same prompt and the same candles and watch it reason live, instead of guessing from logs.
- **Playing a trading idea forward through an entire time series** (Simulation/Run) before turning it on for real.
- **Comparing prompt variants** — run two different wordings against exactly the same candles and put the answers side by side.
- **Comparing reasoning-effort levels** — ask the same question at `low` vs. `high` to see whether more reasoning actually produces better analysis or just costs time.

**What the PWB is not:** not a replacement for the Snapshot Designer (which remains the source of truth for the production data pipeline), and not a place where prompt edits automatically go live — see the warning in Section 7.

---

## Table of Contents

1. [Page Layout](#1-page-layout)
2. [Workbench Config — New / Load / Save / Delete](#2-workbench-config--new--load--save--delete)
3. [Candle-Loading Bar](#3-candle-loading-bar)
4. [Simulation Controls in the Header Bar](#4-simulation-controls-in-the-header-bar)
5. [Chart Area](#5-chart-area)
6. [Left Column: Chat](#6-left-column-chat)
7. [Left Column: Prompt](#7-left-column-prompt)
8. [Right Column: Analyse Tab](#8-right-column-analyse-tab)
9. [Right Column: Simulation Tab](#9-right-column-simulation-tab)
10. [Right Column: LLM Context Tab](#10-right-column-llm-context-tab)
11. [Agent Annotation Tools](#11-agent-annotation-tools)
12. [The Frozen-Window Principle: Why It Matters](#12-the-frozen-window-principle-why-it-matters)
13. [Common Problems](#13-common-problems)
14. [Worked Example: Developing a Prompt From Scratch](#14-worked-example-developing-a-prompt-from-scratch)
15. [More Workflows](#15-more-workflows)

---

## 1. Page Layout

Top to bottom, the page consists of:

1. **Workbench config bar** — save/load the whole session as a named preset.
2. **Candle-loading bar** — broker, pair, timeframe, candle count, anchor date, simulation controls.
3. **Chart** — resizable via the drag handle below it (160–800 px).
4. **Bottom area, two columns:**
   - **Left:** `Chat` / `Prompt` tabs
   - **Right:** `Analyse` / `Simulation` / `LLM Context` tabs

---

## 2. Workbench Config — New / Load / Save / Delete

At the very top. Saves or loads a complete Workbench preset under a freely chosen name (autocomplete shows existing names).

| Element | Function |
|---------|---------|
| **New** | Resets the entire Workbench to a blank state — candles, chat, annotations, simulation, prompt, tool blocks, everything. |
| **Name field** | Preset name, with a suggestion list of already-saved presets. |
| **Load** | Loads the preset with this name. |
| **Save** | Saves the current state under this name (overwrites a preset with the same name). |
| **Delete** | Deletes the preset with this name. |

**Stored in the preset:** broker, pair, timeframe, candle count, anchor date, annotation color, step size, auto-trade-status, active chat/prompt tab, active analyse/simulation tab, system prompt, LLM selection, reasoning effort, indicators (Analyse tab), tool_blocks/calculation_blocks/assembly_transform_script (Simulation tab).

**Not part of the preset** (session state, not configuration): the loaded candles, chat history, drawn annotations, current simulation position.

**Recommendation:** the moment a prompt draft starts producing usable answers, save it under its own name right away (e.g. `andrew_krieger_v1`) before experimenting further. Clicking `New` or reloading the page wipes everything with no confirmation — there's no undo. For multiple prompt variants, a naming scheme like `strategy_v1`, `strategy_v2` pays off later when comparing via Load.

> The `LLM Context` tab is a live preview only, not a persisted mode — saving maps it back to `Analyse` automatically so the preset schema stays stable.

---

## 3. Candle-Loading Bar

| Element | Function |
|---------|---------|
| **Broker dropdown** | Only shown with more than one connected broker. With exactly one, the name is shown as plain text instead. |
| **Pair dropdown** | Currency pair, derived from the active agent configurations. |
| **Timeframe buttons** | M5 through D1 (no M1). |
| **Candles** | Number of candles to load, 20–2000. Only reacts on blur or Enter, not on every keystroke. |
| **Anchor date** | Optional. When set, candles are loaded up to `<date> 23:59:59` instead of the newest available. |
| **Load** | Reloads candles. Also triggered automatically on any change to pair/timeframe/candle count/anchor date. |

**Recommendation on candle count:** for a quick prompt test (a handful of questions, fast iteration), 100–200 candles is usually enough — every chat message gets answered faster and more cheaply. For a realistic simulation across several trading days, pick a count that covers the desired period plus some lead-in (e.g. 500 M5 candles ≈ a bit under 2 trading days) — otherwise the simulation runs out sooner than planned.

**Warning — forgetting the anchor date:** if you set an anchor date on purpose to load a specific past situation, it stays active on the next `Load` unless you clear it with `×`. A common source of confusion: you switch pairs, click `Load`, and still get data from weeks ago — because the anchor date was still set. If "why isn't this showing current candles" comes up, check here first.

Loading captures the timestamp of the newest loaded candle as an internal **anchor** (`candle_anchor`), sent with every subsequent chat/simulation/preview request — see [Section 12](#12-the-frozen-window-principle-why-it-matters).

---

## 4. Simulation Controls in the Header Bar

To the right of `Load`, separated by a divider:

| Element | Function |
|---------|---------|
| **Position** | Number field, 0…total. Counts **down**: `total` = the oldest edge of the loaded window (nothing visible), `0` = fully revealed (all candles visible). |
| **Step size** | Number of candles `Step`/`Run` reveal per step. |
| **Step** | Runs exactly one simulation step: Position decreases by `Step size`, the agent gets a message with the newly visible window and is asked to decide (hold/open/close), recording that via `trade_marker` if applicable. |
| **Run / Stop** | Repeats `Step` (500 ms pause between steps) until Position reaches `0` or `Stop` is pressed. |
| **visible: X / Y (candles Y–Position)** | Shown only when Position > 0. |
| **Clear chart** | Removes all agent-drawn annotations from the chart. **Does not** touch the chat history (`Delete` in the Chat tab, Section 6, does that). |
| **Reset** | Resets chart zoom/pan. |

**Recommendation:** always click `Step` once or twice before your first `Run` and read the answers. `Run` calls the LLM automatically and repeatedly — if something's misconfigured (too little visible context, a prompt that sends the agent into a repetitive self-justification loop), `Step` catches it immediately and cheaply; `Run` catches it only after many wasted LLM calls.

**Warning — cost/time on `Run`:** every simulation step is a real LLM call. With `Step size = 3` and 500 loaded candles, that's roughly 165 calls down to Position 0 — with an expensive model or high reasoning effort, a full `Run` can take noticeably long and cost real money. Choose a larger `Step size` when only a rough trend is of interest, or jump `Position` directly to the relevant window instead of starting from `total`.

Candle numbering is consistent everywhere: `#1` = newest candle, `#total` = oldest — the same numbering the agent itself uses when referencing candles (e.g. in `zone_marker`/`trade_marker` calls).

---

## 5. Chart Area

Shows the standard candle chart (same chart component as Chart Analysis) with:

- Overlay indicators and oscillators from the Analyse tab
- Swing-level price lines from the Analyse tab
- Zones, trade lines, and candle markers drawn by the agent (see Section 11)
- In the Simulation tab, additionally: an orange arrow marker labeled "Agent-Grenze" (agent boundary) at the last visible candle whenever `Position` is between `0` and `total` — handy for seeing at a glance where the agent currently "stands" without reading the number fields.

Height is adjustable via the drag handle below it (160–800 px) — a taller chart pays off during a simulation with many trade markers, so the resulting lines don't get lost.

---

## 6. Left Column: Chat

Free-form chat with the agent over the currently loaded candle storage.

### 6.1 Header

| Element | Function |
|---------|---------|
| **→ KB** | Exports the entire visible chat history as a Markdown document into the Knowledgebase. |
| **Delete** (trash icon) | Clears only the chat history. Drawings are untouched (`Clear chart`, Section 4, handles those). |
| **Color swatch** | Color newly drawn annotations will use from now on — already-drawn ones keep their color. |
| **Reasoning-effort dropdown** | `none` / `low` / `medium` / `high`. Defaults to `low`, regardless of the LLM module. |

**Recommendation on the color swatch:** for an A/B comparison — e.g. "question A in red, the same question reworded in blue" — deliberately change the color before each run. That way the chart itself shows which drawing belongs to which question/version, without having to cross-reference the chat history.

**Recommendation on reasoning effort:** start at `low`. Only raise it if answers feel shallow, or if the agent visibly skips steps on multi-part analysis (e.g. "compare the last three swing highs and derive a trend statement"). A blanket high reasoning effort for simple questions just costs time without a noticeable quality gain.

**Warning:** an agent can make plausible-sounding but wrong claims about the chart (e.g. citing the wrong candle number). For anything that matters, push back, or explicitly ask the agent to back up its claim on the chart via `get_annotation`/`candle_marker` instead of answering purely in prose — see Section 11.

### 6.2 Message History

- User messages align right, agent replies align left, each with a copy button.
- Auto-scroll aligns to the start of a new, long reply instead of scrolling it entirely out of view — preserved even if you resize the chat area afterward.

### 6.3 Input Field

`Enter` sends, `Shift+Enter` inserts a line break. By default the agent gets `calculate_indicator`, `zone_marker`, `trade_marker`, `candle_marker`, `get_annotation` (see Section 11).

**Example question that puts the annotation tools to good use:**

> "Look at the last 500 candles. Use `zone_marker` to mark every zone where price bounced at least three times, and briefly explain why you consider it relevant."

A question like this forces the agent to make its claim visible on the chart, instead of just handing you a text description you can't easily verify.

---

## 7. Left Column: Prompt

Editor for the agent's system prompt.

| Element | Function |
|---------|---------|
| **"— load from agent —" dropdown + Load** | Pulls in an existing agent's system prompt (and LLM, if set) from `system.json5`. |
| **LLM dropdown** | Which LLM module Chat/Step/Run use. `— auto —` uses the first available module. |
| **Editor** | Plain-text editor (Monaco, plaintext mode). |

**Recommendation — a typical prompt development cycle:**

1. Either write from scratch, or use "load from agent" to start from an existing, similar agent's prompt.
2. Make one small, targeted change (not several at once — otherwise it's unclear which change caused which effect).
3. Test with 2–3 representative questions in the `Chat` tab.
4. Better or worse than before? Make the next change.
5. Once satisfied: save a preset (Section 2).

**Warning — changes here do NOT go live automatically:** the Workbench prompt editor is completely separate from the real agent's system prompt in `system.json5`. An improvement developed here must be **manually** copied into the agent's configuration (Config → Agent Config) to take effect in live trading. There is no "apply" button that does this automatically.

---

## 8. Right Column: Analyse Tab

Functionally mirrors the Analyse area in Chart Analysis, with one crucial difference: **everything visible here is actually sent to the LLM**, not just drawn on the chart (see Section 10).

### 8.1 Indicators

Same panel as Chart Analysis (EMA, SMA, RSI, ATR, BB, VWAP, SlopeE, SlopeS). For details, see the [Chart Analysis Handbook](ui.action.chart_analysis.en.md#6-indicator-reference-ema-and-sma).

### 8.2 Swing Levels

Same panel as Chart Analysis — with one exception: **no Visible/All toggle.** Swing levels here always refer exclusively to the visible candle window (`Position`).

**Recommendation — test realistically:** if the prompt is ultimately meant for an agent that sees specific indicators/swing levels in production, set up the **same** ones here with the same settings. Testing the prompt without indicators, while the target agent actually works with EMA(20)/EMA(50) in production, makes the test results meaningless — the agent simply "sees" less here than it will in live trading.

---

## 9. Right Column: Simulation Tab

A mini Snapshot Designer for Chat/Step/Run: the same `tool_blocks`/`calculation_blocks`/`assembly_transform_script` editing UI as the real Snapshot Designer, here for testing against the loaded candle storage.

| Element | Function |
|---------|---------|
| **"— load from snapshot profile —" dropdown + Load** | Pulls in tool_blocks/calculation_blocks/assembly_transform_script from an existing Snapshot Profile. |
| **tool_blocks panel** | Same UI as the Snapshot Designer, including per-row "Test". |
| **calculation_blocks panel** | "Test" runs all tool_blocks plus just that one calculation block. |
| **assembly_transform_script** | Optional merge script, same editor as the Snapshot Designer. |
| **Auto Trade-Status einfügen** | Automatically prefixes every Step request with a summary of currently open simulated trades. |
| **FIFO aktivieren** | When enabled, the **oldest** still-open simulated trade must be closed first — `trade_marker` rejects an attempt to close a newer one out of order, with an explanatory error. Mirrors brokers that mandate FIFO closing (e.g. certain US-regulated accounts). Off by default, matching the standard behavior of hedging-capable brokers. |
| **delete of trades accepted** | Off by default. A previously recorded trade leg is treated as filled at the broker and normally can't be deleted, only closed (see Section 11). This checkbox explicitly unlocks `op='delete'` for `trade_marker` for this session — e.g. to clean up an unambiguous tool-usage mistake (wrong candle, wrong tool) before it becomes part of a "real" order history. |
| **Test / Preview** | Assembles the complete snapshot once, without calling the LLM. |

**Effect on Chat/Step/Run:** as soon as at least one `tool_block` is entered, the agent receives the fully assembled snapshot instead of the raw candle text — anchored to the last visible candle. If the list stays empty, the agent gets the plain candle-text block from the Analyse tab.

**Recommendation — which mode to use when:** for pure prompt-wording tuning ("does the answer read the way I want?"), the plain candle-text mode (leave Simulation empty) is usually enough and quicker to set up. But once the question becomes whether the prompt works with a **specific** agent's real production data (including all its tool blocks, calculations, custom transforms), load the matching snapshot profile — otherwise you're strictly testing the LLM's language ability, not its interaction with the real data pipeline.

**Blocked tools:** action tools like `place_order`, `close_position`, `raise_alarm` are categorically unavailable here — a snapshot may only gather data. The four annotation tools (Section 11) are deliberately available here, unlike in the real Snapshot Designer.

---

## 10. Right Column: LLM Context Tab

Shows exactly what the agent would receive as context on the next chat message — without calling the LLM, via the same code a real chat call uses.

| Field | Meaning |
|-------|---------|
| `mode` | `"snapshot"` when tool_blocks are configured, otherwise `"candles"`. |
| `total_candles` / `visible_candles` | Size of the loaded window vs. the visible portion. |
| `candles` | Structured list of the visible candles — display only. |
| `indicators` / `swing_levels` | Currently visible indicators/swing levels. |
| `snapshot` / `snapshot_errors` | The assembled snapshot and errors, only with configured tool_blocks. |
| `system_prompt` | The system prompt exactly as entered in the Prompt tab. |
| `question` | The current text in the chat input field. |
| `user_message` | The exact text the agent receives as its user message. |

**Recommendation:** if an answer looks off or wrong, **check here first** before suspecting the prompt or the LLM. A very common reason for "the agent isn't seeing this" or "the agent is ignoring my indicators" is simply that the data never made it into the `user_message` text (e.g. because an indicator is toggled off in the Analyse tab, or a snapshot profile is quietly returning an error). This tab answers "what did the LLM actually receive" with certainty, no guessing required.

Two separate messages go to the LLM — the system message (the Prompt tab's content verbatim) and the user message (`user_message`). The `candles` field exists purely for display in this tab; the candle data itself only reaches the LLM once, embedded in the `user_message` text block.

---

## 11. Agent Annotation Tools

During chat, the agent can use four sandbox-only tools to record its analysis directly on the chart:

| Tool | Draws | Usage |
|------|-------|-------|
| `zone_marker` | A rectangle over a candle range (e.g. a supply/demand zone) | Write |
| `trade_marker` | An entry/exit point; two matching calls (open/close) form a trade line | Write |
| `candle_marker` | An arrow marker above/below a single candle with free text | Write |
| `get_annotation` | Looks up a previously placed marking and its real candle data by id or candle range | Read |

Every write call has an `op` parameter (`new` / `change` / `delete`) — with one important exception for `trade_marker`, see below:

- **`new`** — creates a new marking, short 2-character id shown as a label prefix, e.g. `[A3] Supply zone`.
- **`change`** — corrects an existing marking; replaces the chart drawing instead of duplicating it.
- **`delete`** — removes an existing marking.

**Special rule for `trade_marker`: a leg is permanent once recorded via `new`.** An `open` or `close` entry simulates an order actually filled at a broker — and in reality that can't be corrected or taken back afterward. So `trade_marker` deliberately deviates from `zone_marker`/`candle_marker` here:

- `op='change'` on a trade leg may **only** set/update the optional free-text `note` field — the candle, direction, and action (open/close) stay exactly as originally recorded. A change call without a `note`, or one that tries to alter the candle/direction, is rejected.
- `op='delete'` is **blocked by default** for a trade leg and returns an explanatory error ("a recorded trade cannot be deleted, only closed"). An open trade can normally only be ended via `action='close'` — never retroactively removed — unless the **"delete of trades accepted"** checkbox in the Simulation tab (Section 9) is explicitly enabled for this session.

This is exactly the fix that stops an agent from quietly rewriting its own entry after the fact (hindsight bias) — every trade record stays an honest, permanent log entry.

**Direction visible on both legs:** `direction` (long/short) isn't just stored on the `open` leg — it's automatically carried over to the matching `close` leg too, and the chart label spells it out as text (`LONG`/`SHORT`), not just implicitly via the open marker's arrow direction.

**Useful pattern:** explicitly ask the agent to review and correct its own markings, e.g.:

> "Double-check your previous zone markings against the real candle data (use `get_annotation`) and correct any that are no longer accurate."

This combines the read (`get_annotation`) and write (`zone_marker` with `op=change`) tools exactly the way they were built to be used — it forces the agent to verify against real data instead of answering purely from memory.

Annotations accumulate client-side across the whole session and are sent back on every request as `existing_annotations`. `Clear chart` (Section 4) clears this collection.

---

## 12. The Frozen-Window Principle: Why It Matters

The Workbench is deliberately built so the loaded chart stays the single data source for the entire session — this isn't an implementation detail, it's the reason the PWB is useful as a testing tool at all:

- **Reproducibility:** without a fixed anchor, every chat request would automatically pull the latest live data. Two questions asked 10 minutes apart could then see slightly different candle windows — comparing two prompt answers would no longer be meaningful, because the underlying data changed between the two tests too.
- **Comparability between prompt variants:** because the window is frozen, you can test prompt A and prompt B back to back against exactly the same candles and compare the answers fairly.
- The agent's direct tool calls (`calculate_indicator`, `get_candles`, `get_swing_levels`) have the last visible candle's timestamp forced as their `start` argument — the agent can't accidentally look beyond the visible window.
- An anchor date in the candle-loading bar only determines which window gets loaded — after that, the same principle applies.

---

## 13. Common Problems

**Problem: the agent answers empty or seems to cut off for no reason.**
Usually caused by too small a token budget combined with a large candle window and high reasoning effort — the model burns its internal thinking budget before producing a visible answer. Fix: reduce candle count, lower reasoning effort, or pick a model with a larger context window.

**Problem: the agent seems to ignore the configured indicators or swing levels.**
Open the `LLM Context` tab (Section 10) first and check whether the data actually shows up in `user_message`. Most common cause: the indicator is toggled off (eye icon) in the Analyse tab — hidden indicators are not sent to the LLM, even though they're still listed in the panel.

**Problem: candle numbers seem to shift between messages.**
Check whether `Load` was clicked again in between, or a setting in the candle-loading bar was changed (that auto-triggers a `Load` and sets a new anchor). Within one session without reloading, numbering stays stable.

**Problem: `Run` seems to hang.**
Every step is a real, synchronous LLM call — with a large candle window, high reasoning effort, or a slow LLM provider, a single step can take several seconds. "Waiting for the agent…" is shown in the chat during this time. Before assuming it's stuck: click `Stop`, wait a moment, and retry with a smaller candle window or a larger `Step size`.

**Problem: an improvement made in the Prompt tab doesn't affect the live agent.**
Not a bug — see Section 7: the PWB prompt must be manually copied into the agent's configuration.

---

## 14. Worked Example: Developing a Prompt From Scratch

Goal: build an agent that trades in the style of the well-known FX trader Andrew Krieger — aggressive, comfortable with large, asymmetric positions, focused on structural liquidity imbalances.

1. **Load candles:** pick a pair and timeframe (e.g. `EUR_USD`, `M15`), set candle count to 500, click `Load`.
2. **Write the prompt** (`Prompt` tab), roughly:
   > "Trade in the style of Andrew Krieger: aggressive, confident in large, asymmetric positions, focused on structural liquidity imbalances rather than short-term noise. Analyze the full 500 loaded candles — not just the last 150 — and use `trade_marker` to mark where you would have entered and where you would have closed the trade."
3. **First test question** in the `Chat` tab: "Analyze the chart and show your trade setup."
4. **Check the answer:** does the agent actually reference older candles, or only the last few? If only the last few — make it more explicit in the prompt that the *entire* loaded window matters (a common LLM tendency is to focus on the most recently shown/numbered data unless told otherwise).
5. **Iterate:** adjust the wording, ask again, until the behavior fits.
6. **Simulate:** set `Position` to `total`, `Step size` to e.g. 20, click `Run`, and watch whether the agent stays consistent with the described style across the whole time series.
7. **Save:** store the preset as `andrew_krieger_v1` once the behavior is convincing.

---

## 15. More Workflows

### 15.1 Simulating a Trading Strategy Over a Time Series

1. Set `Position` to a value greater than 0 (e.g. `total`).
2. Set `Step size` — smaller for fine-grained observation, larger for a quick overview of the overall trend.
3. Optionally load a snapshot profile in the `Simulation` tab, so the agent gets the same context it would in live trading (see the recommendation in Section 9).
4. Click `Step` a few times first, then `Run`.
5. Afterward, review the resulting trade lines on the chart and in the chat history — in particular, whether closed trades were net profitable or lossy, and whether the agent's reasoning holds up.

### 15.2 Fairly Comparing Two Prompt Variants

1. Load candles once (don't reload in between — that would change the comparison baseline).
2. Enter prompt A, set the annotation color to e.g. red, ask a test question.
3. Save the preset as `test_a`.
4. **Don't** use `New` (it clears the loaded candles) — instead, edit the Prompt tab directly to prompt B, change the annotation color to blue, and ask the same question again.
5. Compare the answers and the chart markings (red vs. blue) side by side.

### 15.3 Saving the Current Session as a Preset

1. Enter a name in the name field at the top.
2. Click `Save`.
3. Later, pick the same name and click `Load` — reload candles via `Load` afterward, since they aren't part of the preset.
