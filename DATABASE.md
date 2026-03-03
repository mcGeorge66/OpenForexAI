# DATABASE.md — OpenForexAI Datenbankreferenz

Vollständige Beschreibung aller Tabellen: Zweck, Befüllungszeitpunkt, Schreiber, Leser und mögliche Analysen.

---

## Übersicht

OpenForexAI unterstützt zwei Backends (konfigurierbar via `OPENFOREXAI_DB_BACKEND`):

| Backend | Adapter | Standard-Pfad |
|---|---|---|
| `sqlite` | `SQLiteRepository` | `./data/openforexai.db` |
| `postgresql` | `PostgreSQLRepository` | via Connection-String |

Das Schema wird automatisch beim Start migriert. Die Migration ist idempotent — bereits angewendete Dateien werden übersprungen.

### Migration-Tracking

```
schema_migrations
  filename    TEXT PRIMARY KEY   -- z. B. "001_initial_schema.sql"
  applied_at  TEXT               -- UTC-Timestamp der Anwendung
```

Verwaltet intern durch den Adapter. Nicht für externe Abfragen gedacht.

---

## Tabellen-Übersicht

| Tabelle | Migration | Zweck |
|---|---|---|
| `{BROKER}_{PAIR}_{TF}` | dynamisch | Kerzendaten (M5 primär) |
| `account_status` | dynamisch | Kontostand-Snapshots |
| `order_book_entries` | dynamisch | Authoritative lokale Orderbuch-Kopie |
| `trades` | 001 | Legacy-Trade-Ergebnisse (rückwärtskompatibel) |
| `agent_decisions` | 001 + 003 | Jede LLM-Entscheidung jedes Agenten |
| `trade_patterns` | 002 | Erkannte statistische Muster in Trade-Historie |
| `prompt_candidates` | 002 | Versionierte System-Prompts pro Paar |
| `backtest_results` | 002 | Backtesting-Ergebnisse pro Prompt-Kandidat |
| `agent_conversations` | 003 | Vollständige LLM-Gesprächshistorie pro Zyklus |
| `agent_performance` | 003 | Aggregierte Performance-Snapshots pro Agent |

---

## Dynamische Kerzentabellen

### `{BROKER}_{PAIR}_{TIMEFRAME}`

Beispiele: `OAPR1_EURUSD_M5`, `OAPR1_GBPUSD_M5`

```sql
timestamp    TEXT PRIMARY KEY   -- ISO-8601 UTC, z. B. "2026-03-03T08:00:00+00:00"
open         TEXT               -- Dezimalpreis als String (Decimal-Präzision)
high         TEXT
low          TEXT
close        TEXT
tick_volume  INTEGER
spread       TEXT
```

**Warum:** Nur M5-Kerzen werden vom Broker per API abgefragt. Alle höheren Timeframes (M15, M30, H1, H4, D1) werden vom `DataContainer`-Resampler on-demand aus M5 berechnet. Gespeichert werden primär die M5-Rohdaten; höhere TFs können bei Bedarf ebenfalls persistiert werden (gleiche Tabellenstruktur, anderer TF-Suffix).

**Wann befüllt:**
- Initial beim Systemstart: `BrokerBase` lädt historische M5-Kerzen per Bulk-Insert (`save_candles_bulk`)
- Laufend alle 5 Minuten: Broker-Adapter veröffentlicht `m5_candle_available`; `DataContainer` speichert via `save_candle`

**Schreiber:** `BrokerBase` → `SQLiteRepository.save_candle / save_candles_bulk`

**Leser:**
- `DataContainer` — lädt beim Start fehlende History aus der DB nach
- `get_candles`-Tool — stellt Agenten Kerzenhistorie bereit
- `Backtester` — verwendet historische M5-Daten für Prompt-Tests
- Management-API — `/candles/{pair}` Endpunkt

**Analyse-Möglichkeiten:**
```sql
-- Wie viele M5-Kerzen für EURUSD sind gespeichert?
SELECT COUNT(*) FROM OAPR1_EURUSD_M5;

-- Letzte 10 EURUSD-Kerzen
SELECT * FROM OAPR1_EURUSD_M5 ORDER BY timestamp DESC LIMIT 10;

-- Tagesrange eines bestimmten Tages
SELECT MIN(CAST(low AS REAL)), MAX(CAST(high AS REAL))
FROM OAPR1_EURUSD_M5
WHERE timestamp LIKE '2026-03-03%';
```

---

## `account_status`

```sql
broker_name    TEXT NOT NULL
balance        TEXT               -- Kontostand (Decimal als String)
equity         TEXT               -- Equity inkl. unrealised PnL
margin         TEXT               -- verwendete Margin
margin_free    TEXT               -- verfügbare Margin
leverage       INTEGER
currency       TEXT               -- Kontowährung, z. B. "EUR"
trade_allowed  INTEGER            -- 0 | 1 (SQLite-Boolean)
margin_level   REAL               -- Margin-Level in %, kann NULL sein
recorded_at    TEXT NOT NULL      -- ISO-8601 UTC
PRIMARY KEY (broker_name, recorded_at)
```

**Warum:** Historischer Verlauf des Kontostands ermöglicht Equity-Kurven-Analyse. Der aktuelle Wert wird von Agenten via `get_account_status`-Tool abgefragt.

**Wann befüllt:** `BrokerBase` pollt alle 5 Minuten den Account-Status beim Broker und speichert jeden Snapshot via `save_account_status`.

**Schreiber:** `BrokerBase` (account poll loop)

**Leser:**
- `get_account_status`-Tool → Agenten (Positionsgrößenberechnung, Risk-Check)
- Management-API — `/account/{broker}` Endpunkt
- Supervisor-Agent — prüft Margin-Level vor Trade-Genehmigung

**Analyse-Möglichkeiten:**
```sql
-- Equity-Verlauf der letzten 7 Tage
SELECT recorded_at, CAST(equity AS REAL) AS equity
FROM account_status
WHERE broker_name = 'OAPR1'
  AND recorded_at > datetime('now', '-7 days')
ORDER BY recorded_at;

-- Niedrigste freie Margin (kritische Momente)
SELECT recorded_at, CAST(margin_free AS REAL) AS free
FROM account_status
WHERE broker_name = 'OAPR1'
ORDER BY CAST(margin_free AS REAL) ASC
LIMIT 5;
```

---

## `order_book_entries`

Die **zentrale Trade-Tabelle** des Systems. Eine Zeile pro platziertem Order — von der Signal-Genehmigung bis zur Schließung.

```sql
id                       TEXT PRIMARY KEY          -- UUID
broker_name              TEXT NOT NULL             -- z. B. "OAPR1"
broker_order_id          TEXT                      -- Broker-seitige Order-ID (nach Bestätigung)
pair                     TEXT NOT NULL             -- z. B. "EURUSD"
direction                TEXT NOT NULL             -- "BUY" | "SELL"
order_type               TEXT NOT NULL             -- MARKET | LIMIT | STOP | STOP_LIMIT | TRAILING_STOP
units                    INTEGER NOT NULL

-- Preise
requested_price          TEXT NOT NULL             -- kalkulierter Einstiegspreis des Agenten
fill_price               TEXT                      -- tatsächlicher Füllpreis (nach Broker-Bestätigung)
stop_loss                TEXT
take_profit              TEXT
trailing_stop_distance   TEXT                      -- in Pips (nur TRAILING_STOP)
limit_price              TEXT                      -- LIMIT / STOP_LIMIT
stop_price               TEXT                      -- STOP / STOP_LIMIT

-- Status
status                   TEXT NOT NULL             -- PENDING | OPEN | PARTIALLY_FILLED | CLOSED | REJECTED | CANCELLED

-- Agent-Kontext (Schlüssel für Optimierung)
agent_id                 TEXT NOT NULL             -- z. B. "OAPR1_EURUSD_AA_ANLYS"
prompt_version           INTEGER                   -- Prompt-Version zum Zeitpunkt des Signals
entry_reasoning          TEXT NOT NULL             -- Begründungstext des Agenten
signal_confidence        REAL NOT NULL             -- 0.0–1.0
market_context_snapshot  TEXT NOT NULL             -- JSON: letzter M5-Candle + Indikatorwerte

-- Zeitstempel
requested_at             TEXT NOT NULL             -- Signal-Zeitpunkt
opened_at                TEXT                      -- Broker-Bestätigung
closed_at                TEXT
last_broker_sync         TEXT                      -- letzter Sync-Check

-- Exit-Daten
close_reason             TEXT                      -- SL_HIT | TP_HIT | TRAILING_STOP | AGENT_CLOSED | BROKER_CLOSED | SYNC_DETECTED
close_price              TEXT
close_reasoning          TEXT                      -- Freitext-Notiz zur Schließung
pnl_pips                 TEXT
pnl_account_currency     TEXT

-- Sync
sync_confirmed           INTEGER NOT NULL DEFAULT 0  -- 1 = Broker hat Position bestätigt
```

**Warum:** Diese Tabelle ist die einzige Wahrheitsquelle über alle Trades des Systems. Sie enthält den vollständigen Kontext zum Zeitpunkt der Entscheidung (`market_context_snapshot`, `entry_reasoning`) — das ist das primäre Rohmaterial für den `OptimizationAgent`.

**Wann befüllt:**
- `PENDING`-Eintrag beim Signal-Approval (Supervisor genehmigt)
- Update auf `OPEN` + `fill_price` nach Broker-Bestätigung
- Update auf `CLOSED` beim Schließen (SL/TP/Agent/Sync)
- `last_broker_sync` bei jedem Sync-Zyklus aktualisiert

**Schreiber:** Broker-Agent (`BA`) via `place_order`-Tool → `save_order_book_entry`; Sync-Loop via `update_order_book_entry`

**Leser:**
- `get_open_positions`-Tool — zeigt Agenten offene Positionen
- `get_order_book`-Tool — historische Übersicht
- `OptimizationAgent` — analysiert `market_context_snapshot` + Ergebnisse
- Sync-Loop — prüft PENDING/OPEN-Einträge gegen Broker-API
- Management-API — `/orders/{broker}` Endpunkt

**Analyse-Möglichkeiten:**
```sql
-- Win-Rate nach Paar
SELECT pair,
       COUNT(*) AS total,
       SUM(CASE WHEN CAST(pnl_account_currency AS REAL) > 0 THEN 1 ELSE 0 END) AS wins,
       ROUND(100.0 * SUM(CASE WHEN CAST(pnl_account_currency AS REAL) > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_rate_pct
FROM order_book_entries
WHERE status = 'CLOSED'
GROUP BY pair;

-- Durchschnittlicher PnL nach Close-Grund
SELECT close_reason, AVG(CAST(pnl_account_currency AS REAL)) AS avg_pnl, COUNT(*) AS cnt
FROM order_book_entries
WHERE status = 'CLOSED'
GROUP BY close_reason;

-- Alle Trades mit hohem Confidence-Score die trotzdem verloren
SELECT id, pair, direction, signal_confidence, pnl_account_currency, entry_reasoning
FROM order_book_entries
WHERE status = 'CLOSED'
  AND signal_confidence > 0.8
  AND CAST(pnl_account_currency AS REAL) < 0
ORDER BY pnl_account_currency ASC;

-- Slippage (requested vs. fill)
SELECT pair, AVG(ABS(CAST(fill_price AS REAL) - CAST(requested_price AS REAL))) AS avg_slippage
FROM order_book_entries
WHERE fill_price IS NOT NULL
GROUP BY pair;
```

---

## `trades`

**Legacy-Tabelle** — wird für Rückwärtskompatibilität behalten. Neuere Deployments verwenden primär `order_book_entries`.

```sql
id              TEXT PRIMARY KEY
pair            TEXT NOT NULL
direction       TEXT NOT NULL          -- "BUY" | "SELL"
units           INTEGER NOT NULL
entry_price     TEXT NOT NULL
stop_loss       TEXT NOT NULL
take_profit     TEXT NOT NULL
fill_price      TEXT
pnl             TEXT
status          TEXT NOT NULL          -- PENDING | OPEN | CLOSED | REJECTED
opened_at       TEXT
closed_at       TEXT
close_reason    TEXT                   -- TP | SL | manual | timeout
agent_id        TEXT NOT NULL
broker_order_id TEXT
created_at      TEXT NOT NULL
```

**Wann befüllt:** Via `save_trade` (wird in neuem Code kaum noch direkt aufgerufen; `order_book_entries` ist der Standard).

**Analyse:** Gleiche Grundmuster wie `order_book_entries`, aber ohne `market_context_snapshot` und `entry_reasoning`.

---

## `agent_decisions`

Protokolliert **jede LLM-Entscheidung** jedes Agenten — das vollständige Audit-Log des KI-Systems.

```sql
id               TEXT PRIMARY KEY
agent_id         TEXT NOT NULL          -- z. B. "OAPR1_EURUSD_AA_ANLYS"
agent_role       TEXT NOT NULL          -- trading | technical_analysis | supervisor | optimization
pair             TEXT
decision_type    TEXT NOT NULL          -- signal | hold | approve | reject | analyze | optimize
input_context    TEXT NOT NULL          -- JSON: was der Agent als Input bekam
output           TEXT NOT NULL          -- JSON: was der Agent entschieden hat
llm_model        TEXT NOT NULL          -- z. B. "claude-sonnet-4-6"
tokens_used      INTEGER                -- Gesamte Token-Anzahl (input + output)
latency_ms       REAL                   -- Antwortzeit in ms
decided_at       TEXT NOT NULL          -- ISO-8601 UTC

-- Felder aus Migration 003:
reasoning        TEXT                   -- vollständiger Reasoning-Text des LLM
market_snapshot  TEXT                   -- JSON: Marktdaten zum Entscheidungszeitpunkt
confidence       REAL                   -- 0.0–1.0 (wenn vom Agent ausgegeben)
```

**Warum:** Vollständige Nachvollziehbarkeit aller KI-Entscheidungen. Ermöglicht Post-Mortem-Analyse, Debugging und Kostentracking.

**Wann befüllt:** Am Ende jedes `run_cycle()` — nach jeder LLM-Antwort, unabhängig vom Ergebnis.

**Schreiber:** Jeder Agent via `save_agent_decision` nach abgeschlossenem LLM-Turn.

**Leser:**
- `OptimizationAgent` — Muster-Erkennung über Entscheidungssequenzen
- Management-API — `/decisions/{agent_id}` Endpunkt
- Monitoring / Debugging

**Analyse-Möglichkeiten:**
```sql
-- Token-Kosten pro Agent pro Tag
SELECT agent_id,
       DATE(decided_at) AS day,
       SUM(tokens_used) AS total_tokens,
       COUNT(*) AS decisions
FROM agent_decisions
GROUP BY agent_id, day
ORDER BY day DESC, total_tokens DESC;

-- Durchschnittliche LLM-Latenz nach Modell
SELECT llm_model, AVG(latency_ms) AS avg_ms, MAX(latency_ms) AS max_ms
FROM agent_decisions
GROUP BY llm_model;

-- Verhältnis approve/reject des Supervisors
SELECT decision_type, COUNT(*) AS cnt
FROM agent_decisions
WHERE agent_role = 'supervisor'
GROUP BY decision_type;

-- Welche Entscheidungen haben zum Signal "hold" geführt?
SELECT decided_at, pair, output
FROM agent_decisions
WHERE decision_type = 'hold'
ORDER BY decided_at DESC
LIMIT 20;
```

---

## `agent_conversations`

Speichert die **vollständige LLM-Nachrichtenhistorie** pro Agent-Zyklus (Session).

```sql
id          TEXT PRIMARY KEY       -- UUID
agent_id    TEXT NOT NULL          -- z. B. "OAPR1_EURUSD_AA_ANLYS"
session_id  TEXT NOT NULL          -- UUID, eine neue pro run_cycle()-Aufruf
messages    TEXT NOT NULL          -- vollständige JSON-Nachrichtenliste (system, user, assistant, tool_result)
turn_count  INTEGER DEFAULT 0      -- Anzahl LLM-Turns in dieser Session
started_at  TEXT NOT NULL          -- ISO-8601 UTC
updated_at  TEXT NOT NULL          -- ISO-8601 UTC (Upsert bei jedem Turn)
UNIQUE (agent_id, session_id)
```

**Warum:** Vollständige Reproduzierbarkeit jedes Zyklus. Ermöglicht genaue Analyse, warum ein Agent zu einer bestimmten Entscheidung gekommen ist — inklusive aller Tool-Calls und Zwischenschritte.

**Wann befüllt:** Upsert nach jedem LLM-Turn innerhalb von `run_cycle()`. Eine Session endet mit dem Zyklus.

**Schreiber:** Agent (`agent.py`) via Repository nach jedem Turn.

**Leser:**
- Debugging und Post-Mortem-Analyse
- Prompt-Engineering (Sichtung realer Konversationsabläufe)
- Potentiell `OptimizationAgent` für tiefe Verhaltensanalyse

**Analyse-Möglichkeiten:**
```sql
-- Sessions mit vielen Turns (komplexe Entscheidungen)
SELECT agent_id, session_id, turn_count, started_at
FROM agent_conversations
ORDER BY turn_count DESC
LIMIT 10;

-- Alle Sessions eines Agenten heute
SELECT session_id, turn_count, started_at, updated_at
FROM agent_conversations
WHERE agent_id = 'OAPR1_EURUSD_AA_ANLYS'
  AND DATE(started_at) = DATE('now')
ORDER BY started_at DESC;
```

---

## `agent_performance`

Append-only Tabelle mit **aggregierten Performance-Snapshots** pro Agent und Paar.

```sql
id               TEXT PRIMARY KEY       -- UUID
agent_id         TEXT NOT NULL
pair             TEXT NOT NULL
total_decisions  INTEGER DEFAULT 0
trades_opened    INTEGER DEFAULT 0
trades_closed    INTEGER DEFAULT 0
win_count        INTEGER DEFAULT 0
loss_count       INTEGER DEFAULT 0
total_pnl        REAL DEFAULT 0.0
period_start     TEXT NOT NULL          -- ISO-8601 UTC (Anfang des Auswertungsfensters)
period_end       TEXT NOT NULL          -- ISO-8601 UTC
recorded_at      TEXT NOT NULL          -- ISO-8601 UTC (Zeitpunkt des Snapshots)
```

**Warum:** Leichtgewichtiger Zugriff auf Performance-Kennzahlen ohne aufwändige Aggregation über `order_book_entries` oder `agent_decisions`. Dient als Zeitreihe für Trend-Analyse.

**Wann befüllt:** Periodisch vom `OptimizationAgent` oder Supervisor — nach abgeschlossenen Auswertungsfenstern.

**Schreiber:** `OptimizationAgent` / Supervisor via `save_agent_performance` (Repository-Methode).

**Leser:**
- Management-API — Performance-Dashboard
- `OptimizationAgent` — Baseline für Prompt-Vergleich
- Externe Reporting-Tools

**Analyse-Möglichkeiten:**
```sql
-- Win-Rate-Trend eines Agenten über Zeit
SELECT recorded_at,
       ROUND(100.0 * win_count / NULLIF(trades_closed, 0), 1) AS win_rate_pct,
       total_pnl
FROM agent_performance
WHERE agent_id = 'OAPR1_EURUSD_AA_ANLYS'
ORDER BY recorded_at;

-- Bester Agent nach kumulativem PnL
SELECT agent_id, pair, SUM(total_pnl) AS cum_pnl
FROM agent_performance
GROUP BY agent_id, pair
ORDER BY cum_pnl DESC;
```

---

## `trade_patterns`

Statistisch erkannte Muster in der Trade-Historie. Input für den Prompt-Evolver.

```sql
id                    TEXT PRIMARY KEY
pair                  TEXT NOT NULL
pattern_type          TEXT NOT NULL   -- session_bias | direction_bias | entry_timing | sl_placement
description           TEXT            -- menschenlesbare Beschreibung
frequency             INTEGER         -- wie oft das Muster in den Daten vorkam
win_rate_when_present REAL            -- Win-Rate der Trades, bei denen dieses Muster vorlag
avg_pnl_when_present  REAL            -- durchschnittlicher PnL bei Mustern
conditions            TEXT            -- JSON: z. B. {"session": "london", "rsi": ">70"}
detected_at           TEXT NOT NULL
sample_size           INTEGER         -- Anzahl der analysierten Trades
```

**Warum:** Formalisiertes Gedächtnis des `OptimizationAgent`. Erkannte Muster werden als Wissen für die Prompt-Evolution gespeichert und referenziert.

**Wann befüllt:** `OptimizationAgent` nach Analyse der `order_book_entries`-Historie — typisch nach einer Mindestanzahl abgeschlossener Trades.

**Schreiber:** `OptimizationAgent` via `save_pattern`

**Leser:**
- `OptimizationAgent` — Basis für `PromptCandidate`-Erstellung
- `get_patterns` — Management-API / Debugging

**Analyse-Möglichkeiten:**
```sql
-- Muster mit der höchsten Win-Rate (mind. 20 Samples)
SELECT pair, pattern_type, description, win_rate_when_present, sample_size
FROM trade_patterns
WHERE sample_size >= 20
ORDER BY win_rate_when_present DESC
LIMIT 10;

-- Alle bekannten Muster für EURUSD
SELECT pattern_type, description, win_rate_when_present, avg_pnl_when_present
FROM trade_patterns
WHERE pair = 'EURUSD'
ORDER BY detected_at DESC;
```

---

## `prompt_candidates`

Versionierte System-Prompts pro Währungspaar. Immer nur ein Kandidat pro Paar ist aktiv (`is_active = 1`).

```sql
id              TEXT PRIMARY KEY
pair            TEXT NOT NULL
version         INTEGER NOT NULL       -- monoton steigend pro Paar
system_prompt   TEXT NOT NULL          -- vollständiger System-Prompt-Text
rationale       TEXT                   -- Begründung für die Änderung
source_patterns TEXT                   -- JSON-Array der TradePattern-UUIDs, die diesen Prompt motivierten
is_active       INTEGER DEFAULT 0      -- 0 | 1 (SQLite-Boolean)
created_at      TEXT NOT NULL
```

**Warum:** Ermöglicht kontrollierte, datengesteuerte Prompt-Evolution. Jede Änderung ist versioniert und auf spezifische Muster zurückführbar. Rollback auf ältere Versionen ist jederzeit möglich.

**Wann befüllt:** `OptimizationAgent` erstellt einen neuen Kandidaten nach erfolgreicher Mustererkennung. Aktivierung erfolgt nach positivem Backtest (`is_active` wird via UPDATE gesetzt).

**Schreiber:** `OptimizationAgent` via `save_prompt_candidate`

**Leser:**
- `ConfigService` — liefert aktiven Prompt an Agenten via `AGENT_CONFIG_RESPONSE`
- `get_best_prompt` — gibt den aktuell aktiven Prompt zurück
- Management-API — Prompt-Versionshistorie

**Analyse-Möglichkeiten:**
```sql
-- Alle Prompt-Versionen für EURUSD (neueste zuerst)
SELECT version, is_active, rationale, created_at
FROM prompt_candidates
WHERE pair = 'EURUSD'
ORDER BY version DESC;

-- Welche Patterns haben den aktuell aktiven Prompt begründet?
SELECT source_patterns
FROM prompt_candidates
WHERE pair = 'EURUSD' AND is_active = 1;
```

---

## `backtest_results`

Ergebnisse der Simulation eines `PromptCandidate` auf historischen M5-Daten.

```sql
id                    TEXT PRIMARY KEY
prompt_candidate_id   TEXT NOT NULL      -- FK → prompt_candidates.id
pair                  TEXT NOT NULL
period_start          TEXT               -- Backtest-Zeitraum Anfang
period_end            TEXT               -- Backtest-Zeitraum Ende
total_trades          INTEGER
win_rate              REAL               -- 0.0–1.0
total_pnl             REAL
max_drawdown          REAL
sharpe_ratio          REAL
vs_baseline_pnl_delta REAL               -- PnL-Delta vs. vorherigem aktiven Prompt (positiv = besser)
completed_at          TEXT NOT NULL
FOREIGN KEY (prompt_candidate_id) REFERENCES prompt_candidates(id)
```

**Warum:** Vor dem Aktivieren eines neuen Prompts wird er auf historischen Daten getestet. Nur wenn `vs_baseline_pnl_delta > 0` (und weitere Schwellwerte erfüllt), wird der Kandidat aktiviert.

**Wann befüllt:** `Backtester` via `scripts/run_backtest.py` oder automatisch durch `OptimizationAgent` nach Prompt-Erstellung.

**Schreiber:** `Backtester` via `save_backtest_result`

**Leser:**
- `OptimizationAgent` — Entscheidung über Prompt-Aktivierung
- Management-API — Backtest-Dashboard
- Externe Reporting-Tools

**Analyse-Möglichkeiten:**
```sql
-- Alle Backtests für EURUSD, sortiert nach Sharpe-Ratio
SELECT b.completed_at, b.total_trades, b.win_rate, b.total_pnl,
       b.sharpe_ratio, b.vs_baseline_pnl_delta, p.version
FROM backtest_results b
JOIN prompt_candidates p ON b.prompt_candidate_id = p.id
WHERE b.pair = 'EURUSD'
ORDER BY b.sharpe_ratio DESC;

-- Hat der letzte Prompt-Wechsel wirklich etwas gebracht?
SELECT p.version, b.vs_baseline_pnl_delta, b.win_rate, b.total_pnl
FROM backtest_results b
JOIN prompt_candidates p ON b.prompt_candidate_id = p.id
WHERE p.is_active = 1
ORDER BY b.completed_at DESC
LIMIT 1;
```

---

## Datenfluß-Diagramm

```
Broker-API (alle 5 min)
    │
    ├─► {BROKER}_{PAIR}_M5          (save_candle / save_candles_bulk)
    └─► account_status              (save_account_status)

Agent (LLM-Zyklus)
    │
    ├─► agent_decisions             (save_agent_decision)     — jede LLM-Entscheidung
    └─► agent_conversations         (upsert)                  — vollständige Gesprächshistorie

Signal genehmigt → Order platziert
    │
    └─► order_book_entries          (save_order_book_entry)   — PENDING

Broker bestätigt Fill
    │
    └─► order_book_entries          (update_order_book_entry) — OPEN + fill_price

Trade geschlossen (SL/TP/Agent)
    │
    └─► order_book_entries          (update_order_book_entry) — CLOSED + PnL

OptimizationAgent (periodisch)
    │
    ├─► trade_patterns              (save_pattern)
    ├─► prompt_candidates           (save_prompt_candidate)
    ├─► backtest_results            (save_backtest_result)
    └─► agent_performance           (save_agent_performance)
```

---

## Nützliche Allgemein-Abfragen

```sql
-- Datenbankgröße pro Tabelle (SQLite)
SELECT name,
       SUM(pgsize) / 1024 AS size_kb
FROM dbstat
GROUP BY name
ORDER BY size_kb DESC;

-- Welche Candle-Tabellen existieren?
SELECT name FROM sqlite_master
WHERE type = 'table'
  AND name GLOB '*_M5'
ORDER BY name;

-- Gesamtübersicht: offene Positionen
SELECT broker_name, pair, direction, units, requested_price, signal_confidence, requested_at
FROM order_book_entries
WHERE status IN ('PENDING', 'OPEN', 'PARTIALLY_FILLED')
ORDER BY requested_at DESC;

-- Migrations-Status
SELECT filename, applied_at FROM schema_migrations ORDER BY applied_at;
```
