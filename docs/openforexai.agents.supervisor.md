# agents/supervisor — Risk Management

Risk management components used by Broker Agents to validate trade signals before execution. The supervisor acts as a safety gate between analysis and execution.

## Files

| File | Purpose |
|---|---|
| `risk_engine.py` | Stateless risk assessment — validates signals against configured limits |
| `correlation_checker.py` | Pair correlation analysis for portfolio diversification constraints |

---

## `risk_engine.py` — Risk Engine

A stateless function-based risk checker. Given a trade signal and current account state, it returns an approval decision.

### Checks Performed

| Check | Description |
|---|---|
| **Drawdown limit** | Current equity drawdown must be below `max_drawdown_pct` |
| **Max open positions** | Cannot exceed `max_open_positions` |
| **Position sizing** | Trade size must be within `max_position_size` |
| **Risk per trade** | Calculated risk (size × stop distance) must not exceed `risk_per_trade_pct` of balance |
| **Correlation exposure** | No two highly correlated pairs (> threshold) may be open simultaneously |

### Usage

```python
from openforexai.agents.supervisor.risk_engine import RiskEngine

engine = RiskEngine(risk_parameters)
assessment = engine.assess(
    signal=trade_signal,
    account=account_status,
    open_positions=positions,
    correlation_matrix=correlation_matrix,
)

if assessment.approved:
    # proceed with order placement
else:
    # log assessment.reason and reject signal
```

### Approval Mode Integration

When a BA agent's `place_order` tool has `approval_mode = "supervisor"`:

```
BA agent LLM calls place_order(...)
    │
ToolDispatcher detects approval_mode = "supervisor"
    │
Publishes SIGNAL_GENERATED event
    │
Supervisor component evaluates risk
    │
Publishes SIGNAL_APPROVED or SIGNAL_REJECTED
    │
ToolDispatcher receives response (15s timeout)
    └── approved → executes place_order
    └── rejected → returns error to LLM
```

---

## `correlation_checker.py` — Correlation Checker

Computes rolling Pearson correlation between currency pairs to prevent over-exposure to correlated positions.

### How It Works

```python
checker = CorrelationChecker(data_container)
matrix = await checker.compute_matrix(
    broker_name="OAPR1",
    pairs=["EURUSD", "GBPUSD", "EURGBP"],
    timeframe="H1",
    lookback=50,  # candles
)
# Returns CorrelationMatrix with pairwise correlations
```

### Example Output

```
          EURUSD  GBPUSD  EURGBP
EURUSD     1.00    0.87    0.23
GBPUSD     0.87    1.00   -0.41
EURGBP     0.23   -0.41    1.00
```

If `EURUSD` and `GBPUSD` correlation is `0.87` (> 0.85 threshold), the risk engine will reject a `GBPUSD LONG` signal if a `EURUSD LONG` position is already open.

### Configuration

Risk parameters are configured per-agent in `system.json5`. A typical BA agent receives risk parameters as part of its system prompt context, or from a GA agent that manages portfolio-level risk.

---

## Risk Parameters Model

Defined in `models/risk.py`:

```python
class RiskParameters(BaseModel):
    max_drawdown_pct: float        # e.g. 5.0 = max 5% drawdown
    max_position_size: float       # max units per trade
    max_open_positions: int        # max simultaneous open trades
    max_correlated_exposure: float # max correlation between open positions
    risk_per_trade_pct: float      # % of balance to risk per trade
    correlation_threshold: float   # above this → positions considered correlated
```

