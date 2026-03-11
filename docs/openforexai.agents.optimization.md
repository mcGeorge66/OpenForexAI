[Back to Documentation Index](./README.md)

# agents/optimization — Prompt & Strategy Optimization

Automated optimization of agent system prompts using backtesting, pattern detection, and evolutionary algorithms. This subsystem allows the system to improve its trading prompts over time based on historical performance.

## Files

| File | Purpose |
|---|---|
| `backtester.py` | Replays historical candle data to evaluate prompt candidates |
| `pattern_detector.py` | Detects recurring trade patterns in historical decisions |
| `prompt_evolver.py` | Evolves prompts using a genetic-algorithm-inspired approach |

---

## `backtester.py` — Backtester

Evaluates a system prompt candidate by replaying historical M5 candles through the analysis pipeline and simulating trades.

### How It Works

```
Backtester.run(candidate, pair, start, end)
    │
    1. Load M5 candles from DB for the backtest period
    2. For each time step:
       a. Present candle history to the LLM (using candidate's prompt)
       b. Capture the analysis output (BIAS_LONG / BIAS_SHORT / NEUTRAL)
       c. Simulate entry/exit based on the bias
    3. Compute performance metrics:
       - Win rate
       - Total P&L
       - Max drawdown
       - Sharpe ratio
    4. Save BacktestResult to DB
    5. Return BacktestResult
```

### Key Design

- The backtester uses the **real LLM** (not a mock) to get authentic analysis results
- Candles are fed in historical order — the LLM never sees future data
- Trade simulation uses simple fixed SL/TP rules (configurable)
- Results are stored in the `backtest_results` table for later comparison

---

## `pattern_detector.py` — Pattern Detector

Analyses historical `agent_decisions` records to detect recurring patterns that correlate with winning or losing trades.

### Detected Pattern Types

| Type | Description |
|---|---|
| `session_bias` | Trades placed during specific session have higher win rate |
| `direction_bias` | One direction (LONG/SHORT) consistently outperforms |
| `entry_timing` | Entries at certain times of day or after certain events perform better |
| `sl_placement` | Stop-loss distance correlates with outcomes |

### Output

Each detected pattern is saved to the `trade_patterns` table with:
- Occurrence frequency
- Win rate when pattern is present
- Average P&L when pattern is present
- Conditions that define the pattern (JSON)

These patterns are then used by `prompt_evolver.py` to generate improved prompts.

---

## `prompt_evolver.py` — Prompt Evolver

Uses a genetic-algorithm-inspired approach to evolve system prompts based on detected patterns and backtest results.

### Evolution Cycle

```
1. SELECT current best-performing prompt candidates from DB
2. DETECT patterns in recent trade history (via PatternDetector)
3. GENERATE new candidates:
   a. Mutate existing prompts (adjust thresholds, add pattern-based rules)
   b. Combine elements from multiple high-performers
4. BACKTEST new candidates (via Backtester)
5. PROMOTE the best new candidate:
   a. Set is_active=1 in DB
   b. Publish PROMPT_UPDATED event → AA agents receive and update their prompts
6. ARCHIVE losers
```

### Prompt Update Flow

```
PromptEvolver publishes PROMPT_UPDATED
    │
    └── routing rule "ba_prompt_update_to_aa" →  AA agents (same broker)
            │
            AA agent receives PROMPT_UPDATED
            └── updates self._system_prompt
                (no restart needed)
```

### Triggering Optimization

Optimization is triggered by:
- A GA (Global Agent) running on a scheduled timer
- Manual trigger via `POST /events` endpoint (inject `OPTIMIZATION_COMPLETE`)
- A configurable number of completed trade cycles

---

## Integration with the Agent System

The optimization components are used by GA agents with the appropriate system prompt. A typical Global Optimization Agent:

```json
"GLOBL_ALL..._GA_OPTIM": {
  "type": "GA",
  "llm": "azure_openai",
  "timer": {"enabled": true, "interval_seconds": 86400},
  "event_triggers": ["optimization_complete"],
  "system_prompt": "You are the optimization agent. Analyse trade history, detect patterns, and evolve trading prompts."
}
```

The GA calls the optimization tools in its LLM tool-use cycle.

