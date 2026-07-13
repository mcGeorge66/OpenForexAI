[Back to Config](ui.config.en.md)

# Information

`Information` is a freeform Markdown editor for the file `config/config.md`. It provides a read/edit toggle for project documentation, strategy notes, and any reference content you want to keep alongside your trading configuration. The file is not used by the system — it exists purely for human reference.

---

## What Is config/config.md?

`config/config.md` is a plain Markdown file stored in your configuration directory. It has no effect on system behavior: no agent reads it, no snapshot references it, and no LLM is given its contents. It is purely a documentation file for the people operating the system.

Changes are saved directly to disk via the management API and are immediately visible to anyone who reloads the Information page.

---

## Interface

### View Mode

The default state. Renders `config/config.md` as formatted Markdown: headings, bold/italic, tables, code blocks, links, and horizontal rules are all displayed correctly.

### Edit Mode

Activated by the **Edit** button. Shows the raw Markdown source in a text editor.

### Controls

| Control | Function |
|---|---|
| **Edit** | Switches from view mode to edit mode |
| **Save** | Writes the current editor content to `config/config.md` and returns to view mode |
| **Cancel** | Discards unsaved changes and returns to view mode without saving |

---

## What to Put Here

The Information page is a blank canvas. Use it for anything that helps you or your team understand and operate the system. The following sections describe common practical uses.

### Trading Strategy Documentation

Document the strategy that your agents are configured to follow. This is valuable context when you revisit the configuration months later or when another person takes over operations.

Useful content:

- Strategy name and description
- Entry conditions the LLM is prompted to look for
- Exit and stop-loss logic
- Which pairs and timeframes the strategy is designed for
- Performance expectations and known limitations
- Rationale for key prompt decisions

Example:

```markdown
## Strategy: EUR/USD H1 Trend Continuation

This setup looks for H1 trend continuation with M5 entry timing.

**Entry conditions:**
- H1 EMA20 > EMA50 (bullish) or EMA20 < EMA50 (bearish)
- Price pulled back to H1 EMA20 level
- M5 shows rejection candle or momentum shift
- ATR > 10 pips (sufficient volatility)

**No-trade conditions:**
- Within 30 min of major news event
- H1 ATR expanding rapidly (avoid news spikes)
- DXY moving strongly against the intended direction
```

### Risk Rules and Position Sizing

Document your risk management rules so they are visible alongside the configuration that implements them.

```markdown
## Risk Rules

- Max risk per trade: 1% of equity
- Max open trades simultaneously: 3
- Max total open risk: 3% of equity
- No trading between 22:00–01:00 UTC (thin liquidity)
- Stop-loss always set at ATR × 1.5 from entry
- Take-profit at ATR × 2.5 (1:1.67 R:R minimum)
```

### Broker and Account Setup Notes

Record broker-specific information that is useful for troubleshooting or onboarding.

```markdown
## Broker Setup

**Broker:** OANDA
**Account type:** Live / Standard
**Base currency:** EUR
**Module file:** config/adapters/broker_oanda_live.json5

**Symbols configured:**
- EURUSD (pip size: 0.0001, lot: 100,000)
- GBPUSD (pip size: 0.0001, lot: 100,000)
- USDJPY (pip size: 0.01, lot: 100,000)

**Notes:**
- OANDA uses fractional pips — prices have 5 decimal places
- Minimum lot size: 0.001 (1,000 units)
```

### LLM Model Notes

Document which models you are using and why, plus any observations about their behavior.

```markdown
## LLM Configuration

**Analysis agents (AA):** GPT-4o
- Temperature: 0.2
- Max tokens: 800
- Chosen for consistent structured output and reliable tool use

**Broker agents (BA):** GPT-4o-mini
- Temperature: 0.1
- Max tokens: 400
- Lower cost; BA decisions are rule-following, not complex analysis

**Observations:**
- GPT-4o tends to over-qualify signals when ATR is borderline
- Prompt change 2026-04-10: added "do not hedge in uncertainty — choose one direction" improved signal rate
```

### Configuration Change Log

Track significant configuration changes so you can understand what changed and when.

```markdown
## Change Log

### 2026-06-01
- Added bridge tool `ask_ga_outlook` to EUR/USD and GBP/USD AA agents
- Increased BA agent timeout from 30s to 60s after timeout errors during volatile sessions

### 2026-05-15
- Switched AA agents from GPT-4o-mini to GPT-4o — quality improvement noticeable
- Adjusted ATR multipliers: SL from 1.2 to 1.5, TP from 2.0 to 2.5

### 2026-05-01
- Initial live deployment
- EUR/USD H1 and GBP/USD H1 agents active
```

### Agent Architecture Notes

For complex deployments with many agents, document the intended architecture.

```markdown
## Agent Architecture

### Active Agents

| Agent ID | Role | Pair | Timeframe |
|---|---|---|---|
| GLOBL-ALL___-GA-ANLYS | Global analysis | All | Hourly trigger |
| OAPR1-EURUSD-AA-ANLYS | Pair analysis | EUR/USD | H1 |
| OAPR1-GBPUSD-AA-ANLYS | Pair analysis | GBP/USD | H1 |
| OAPR1-EURUSD-BA-TRADE | Trade execution | EUR/USD | Signal-triggered |
| OAPR1-GBPUSD-BA-TRADE | Trade execution | GBP/USD | Signal-triggered |

### Signal Flow

1. H1 candle close → triggers AA agents for each pair
2. AA agent optionally queries GA agent via bridge tool
3. AA agent produces analysis_result event with signal (or no-trade)
4. EC Relay applies time/news filters
5. BA agent receives approved signal, calculates sizing, places order
```

### Session and Time Zone Reference

Keep a quick reference for your trading session schedule.

```markdown
## Session Reference

All times UTC:

| Session | Open | Close | Notes |
|---|---|---|---|
| Sydney | 22:00 | 07:00 | Low liquidity for majors |
| Tokyo | 00:00 | 09:00 | JPY pairs most active |
| London | 07:00 | 16:00 | Highest EUR/GBP liquidity |
| New York | 13:00 | 22:00 | USD pairs most active |
| London/NY overlap | 13:00 | 16:00 | Highest volume window |

**No-trade hours configured:** 22:00–01:00 UTC (Event Routing rule)
```

### Performance Notes

Track observations about live performance to inform future prompt and configuration changes.

```markdown
## Performance Observations

### EUR/USD H1 (as of 2026-06-01)
- Win rate: ~58% over last 30 trades
- Best performance: London session, trending days
- Worst performance: Monday Asian session, choppy range
- Known issue: agent sometimes over-confident during news days — consider adding news gate

### GBP/USD H1
- Lower signal frequency than EUR/USD (more conservative prompt)
- Average R:R on winning trades: 1.8 — slightly below target of 2.0
- Consider reducing ATR TP multiplier slightly
```

---

## Markdown Formatting Reference

All standard Markdown is supported:

```markdown
# Heading 1
## Heading 2
### Heading 3

**Bold text**
*Italic text*

- Bullet list item
- Another item
  - Nested item

1. Numbered list
2. Second item

| Column 1 | Column 2 |
|---|---|
| Cell | Cell |

`inline code`

\```python
# code block
def example():
    pass
\```

> Blockquote text

---
(horizontal rule)
```

---

## See Also

- [System Config](ui.config.system_config.en.md) — Edit system.json5 directly
- [Agent Config](ui.config.agent_config.en.md) — Agent definitions and settings
- [Decision Prompt](ui.config.decision_prompt.en.md) — LLM system prompts
- [Package Manager](ui.config.package_manager.en.md) — Export and import configuration packages
