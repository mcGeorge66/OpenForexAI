[Back to Config](ui.config.en.md)

# Chartshot Config — Handbook

The **Chartshot Config** page manages named presets for the `chartshot` tool. This tool renders a candle chart server-side (no browser, via `mplfinance`) as a PNG image and hands it to the LLM as an image attachment — the only way an agent actually **sees** a chart visually, instead of reconstructing it purely from numbers.

**When is this worth it?** Pure numeric analysis (OHLC values, indicator numbers) is often enough for an LLM, but some patterns — a clean double bottom, a flag, a breakout from a recognizable channel — are awkward to describe in text, while a vision-capable LLM spots them instantly on an image. Chartshot pays off mainly when the prompt should reason about visual chart patterns, not for pure numeric evaluation (that's what `calculate_indicator`/`get_candles` are for).

Stored under `config/system.json5` → `chartshot`.

---

## 1. How the Image Reaches the LLM

The tool always writes a file to disk and returns an image-marker string:

| `output_mode` | Marker | Behavior |
|---|---|---|
| `keep` | `image[path]` | File is kept after the LLM call |
| `temp` | `imagetmp[path]` | File is deleted after the LLM call |

The LLM adapter automatically recognizes these markers in the tool result and attaches the image to the next LLM request — nothing else needs to be configured.

**Warning:** sending an image to the LLM is noticeably more expensive (and often slower) than plain text. Use `chartshot` sparingly within a snapshot — usually **one** chart image per analysis cycle is enough, alongside the text data you already have, rather than several images for different timeframes.

---

## 2. Left Column: Preset List

| Element | Function |
|---------|---------|
| **Output directory** | Target directory for rendered image files (default: `data/chartshots`), shared by all presets. |
| **Preset list** | All named configurations. `default` cannot be deleted — it's the fallback whenever a tool call names an unknown preset. |
| **"new config name" + [+]** | Creates a new, empty preset with this name. |

**Recommendation:** create a separate, clearly named preset per use case instead of routing everything through `default` — e.g. `trend_h1` (few indicators, H1-focused for trend context) and `entry_m5` (EMA + swing levels, M15/M5-focused for the actual entry decision). That way a snapshot profile can request exactly the right image instead of getting the same, too-busy or too-empty chart for every purpose.

---

## 3. Right Column: Preset Editor

### 3.1 Header

The `AI Assistant` button opens the embedded [AI-Assistant](ui.config.ai_assistant.en.md) chat with context about the preset currently being edited. `Reload` reloads from the server, `Save` writes the entire `chartshot` configuration back to `system.json5`. `Delete` removes the currently selected preset — except `default`.

### 3.2 Output mode

- **temp** — image file is deleted after the LLM has processed it (default, saves disk space).
- **keep** — image file remains on disk.

**Recommendation:** use `temp` for live trading — with multiple agents and frequent cycles, image files pile up quickly otherwise. `keep` is useful while developing a new preset, when you want to check afterward exactly what the LLM actually saw.

### 3.3 Chart style

`dark` or `light` — controls the background and grid colors of the rendered chart. No known effect on LLM analysis quality; purely a matter of taste, or readability when you're checking the images yourself (Section 4).

### 3.4 Description

Free text appended to the LLM prompt whenever this image is used in a snapshot.

**Example:** "This chart shows EURUSD M15 with EMA 20 and key swing levels. Focus on the reaction at the highlighted support zone — specifically, whether price leaves that zone with fading momentum or a clean break."

**Recommendation:** the description should say concretely *what* the LLM should pay attention to, not just restate what's already visible in the image. "Pay particular attention to X" is more valuable than "This chart shows EURUSD".

### 3.5 Indicators

Same panel as Chart Analysis / Prompt Workbench. For details, see the [Chart Analysis Handbook](ui.action.chart_analysis.en.md#6-indicator-reference-ema-and-sma).

**Warning — don't overload it:** every extra indicator makes the image visually denser. Too many overlays/oscillators at once (e.g. four indicators simultaneously) can confuse a vision model rather than help it, the same way an overloaded chart is harder for a human to read. For a preset, prefer 1–2 clearly visible overlays that actually match the question at hand.

### 3.6 Swing Levels

Same panel as Chart Analysis / Prompt Workbench.

### 3.7 Preview (JSON)

At the bottom of the editor: a read-only preview of the exact `system.json5` entry that will be written for this preset on save — useful for a quick sanity check before saving, e.g. to catch an indicator accidentally added twice.

---

## 4. Rendering a Live Preview

The collapsible **Preview** section at the top of the editor lets you test the preset currently being edited against real market data immediately, without saving:

| Field | Function |
|-------|---------|
| **Agent** | Picks a configured agent — automatically fills in its pair and broker. |
| **Broker** / **Pair** | Can also be overridden manually. |
| **Timeframe** | Chart timeframe for the preview. |
| **Candles** | Number of candles (10–500). |
| **Run** | Renders the image server-side with whatever is currently in the editor (including unsaved changes) and displays it inline. |

**Recommendation:** click **Run** after every change to indicators/swing levels, before saving — it's much faster to spot and fix an overly busy image here than to notice it later in a real agent cycle (where you don't get to see the image directly, see the warning below).

**Warning — you normally don't see the image yourself in production:** in live trading, the rendered image goes straight to the LLM, not to the UI. The most reliable way to check whether a preset actually produces usable images is right here in the preview — if in doubt, temporarily set `output_mode: keep`, let one cycle run, and open the file manually in `output_dir` afterward.

The preview file is automatically deleted by the server after being displayed (regardless of the preset's `output_mode`).

---

## 5. Typical Workflow

1. Create a new preset, or edit `default`.
2. Set indicators and swing levels sparingly (see the warning in Section 3.5).
3. Write the `Description` so it tells the LLM what to pay attention to when looking at it (see the example in Section 3.4).
4. In the Preview section, pick an agent/pair/timeframe and click **Run** — is the image clearly readable, or too cluttered?
5. Click `Save`.
6. Reference the preset by name in a `tool_blocks` entry (Snapshot Config or Prompt Workbench) calling the `chartshot` tool.
7. After the first real use: if unsure whether the image is arriving as intended, briefly set `output_mode: keep` and inspect the generated file in `output_dir`.
