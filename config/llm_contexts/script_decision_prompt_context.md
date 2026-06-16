# Script Context: Decision Prompt Text

This document describes the authoring context of a **Decision Prompt** entry in a Decision Prompt Profile.

## Purpose

Each prompt entry contains free-form text that is injected into the LLM system prompt
(mode `replace`) or appended to it (mode `append`). The text instructs the LLM how to
analyse the snapshot and produce a trading decision.

## Placeholder substitution

When **Placeholders** is enabled on a prompt entry, the text is processed by
`_substitute_placeholders()` before being sent to the LLM. Any `{key}` pattern in the text
is replaced with the matching value from the `placeholders` dict written by the selector script.

### Built-in placeholders (always available)
```
{pair}     — trading pair from the agent config, e.g. "EURUSD"
{comment}  — comment field from the agent config
```

### Custom placeholders (set by selector script)
The selector script can write any key into `placeholders`:

```python
# In the selector script:
placeholders["trend"]       = "bullish"
placeholders["rsi_label"]   = "oversold"
placeholders["price"]       = "1.08423"
```

These become available in the prompt text:

```
The current trend is {trend}. RSI state: {rsi_label}. Price: {price}.
```

If a `{key}` has no matching entry in `placeholders`, it is left unchanged.

## Prompt structure tips

### Snapshot context injection
The snapshot JSON is always injected into the LLM input automatically — the prompt text
does not need to reproduce the data. Instead, reference it:

```
Analyse the snapshot data and provide a trading decision for {pair}.
```

### Mode: replace
The prompt text fully replaces the base agent system prompt for this call.
Include all required instructions about output format, risk rules, etc.

### Mode: append
The prompt text is appended to the existing base system prompt.
Use this to add situation-specific instructions without repeating the base.

```
The current market is {trend} with RSI in {rsi_label} territory.
Adjust your confidence threshold accordingly.
```

### Conditional instructions via placeholders
Use the selector script to classify the market and write a label, then
reference it in the prompt:

```
Market regime: {trend}. RSI: {rsi_label}.

If the regime is bullish and RSI is oversold, treat long signals with higher confidence.
If the regime is bearish and RSI is overbought, treat short signals with higher confidence.
Otherwise, be conservative.
```

## Output format instructions

Be explicit about the expected JSON output from the LLM. For example:

```
Respond with a JSON object in this exact format:
{
  "action": "long" | "short" | "none",
  "confidence": 0.0–1.0,
  "reason": "<one-line explanation>"
}
Do not include any text outside the JSON object.
```
