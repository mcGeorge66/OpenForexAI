# VTX Macro vs. OpenForexAI — Systemvergleich

> Erstellt: 2026-06-17 | Basis: Live-Analyse vtxmacro.com/ai/trader-6032c4

---

## Kurzprofil beider Systeme

| | **VTX Macro** | **OpenForexAI** |
|---|---|---|
| Typ | SaaS Web-App | Self-hosted Python-System |
| Markt | Krypto (Hyperliquid Perps) | Forex (OANDA, MetaTrader 5) |
| Modelle | Google Gemma/Gemini (free tier) | Claude Opus, GPT-4o, Azure, LM Studio, Ollama |
| Architektur | Monolithisch, Single-Agent | Multi-Agent (AA → BA → GA), Event-Bus |
| Hosting | Fremder Server | Lokal / eigene Infra |
| UI | TradingView-Chart, vollständig | Monitoring-CLI, Management-API |

---

## OpenForexAI — Stärken gegenüber VTX Macro

### 1. Modellqualität — entscheidender Vorteil
VTX verwendet standardmäßig `gemma-4-31b-it` (kostenlos, 262K Kontext). OpenForexAI nutzt Claude Opus oder GPT-4o — deutlich besseres Reasoning, besseres Situationsbewusstsein, zuverlässigere Structured Outputs. Beim autonomen Trading ist das der größte einzelne Qualitätshebel überhaupt.

### 2. Multi-Agent-Pipeline
```
AA (Analysis) → BA (Execution) → GA (Optimization)
```
VTX hat einen einzigen „Main Model"-Loop. OpenForexAI trennt Analyse, Ausführung und Optimierung auf drei Agenten-Typen mit separaten Verantwortlichkeiten und separaten LLM-Budgets. Das ermöglicht z. B. ein günstiges Modell für Analyse und ein starkes für Execution-Entscheidungen.

### 3. Prompt-Evolution durch GA
Der GA-Agent backtested Prompts periodisch und entwickelt sie weiter (`prompt_candidates`-Tabelle mit Scores). VTX hat kein vergleichbares Feature — Prompts sind statisch, solange der User sie manuell ändert.

### 4. Vollständiges Audit-Trail
Jede LLM-Entscheidung landet in `agent_decisions` (Tokens, Latenz, Input/Output). VTX zeigt Kosten pro Modell an, aber speichert keine Entscheidungshistorie für Analyse.

### 5. Temperature 0.1 vs. 1.0
OpenForexAI setzt `temperature: 0.1` — deterministische, reproduzierbare Entscheidungen. VTX läuft mit 1.0 (maximale Kreativität) — für Trading kontraproduktiv, erhöht Variance ohne Edge.

### 6. Tool-System mit Approval-Modi
11 Tools mit dreistufiger Genehmigung (`direct` / `supervisor` / `human`). VTX hat kein vergleichbares Approval-System — der Bot handelt oder handelt nicht.

### 7. Self-hosted — Datensouveränität
Keine Abhängigkeit von einem SaaS-Anbieter, keine Nutzerdaten auf fremden Servern, keine monatlichen Fees, keine API-Key-Exposition gegenüber Dritten.

### 8. Erweiterbarkeit
Hexagonale Architektur: neuer Broker, neues LLM, neues Tool = eine Datei implementieren + Eintrag in Config. VTX bietet keine Erweiterungsschnittstellen.

### 9. Lokale Modelle (LM Studio / Ollama)
Nullkosten-Betrieb für Screener-äquivalente Aufgaben oder Tests. VTX bietet Venice AI als günstige Alternative, aber kein echtes Offline-Betriebsmodell.

---

## Features die VTX als UI-Checkbox hat — in OpenForexAI bereits durch Konfiguration abbildbar

VTX hat diese Features eingebaut und per Schieberegler konfigurierbar. OpenForexAI hat keine UI dafür, aber die Architektur deckt alle drei Fälle bereits ab — sie müssen nur konfiguriert werden.

---

### 1. Market Regime Detection (Chop-Filter)

**Was VTX macht:** Vor jedem Trade-Zyklus prüft VTX ADX, Chop Index und ATR%. Ist der Markt nicht im Trend, wird der LLM-Aufruf gar nicht erst gestartet.

**In OpenForexAI:** Zwei gleichwertige Wege:

**Weg A — EC als vorgelagerter Filter im Event-Flow**

Ein Event-Condition-Handler wird zwischen den M5-Trigger und den AA-Agenten geschaltet. Er berechnet die Regime-Indikatoren und lässt das Event nur durch wenn der Markt handelbar ist.

```json5
// config/RunTime/event_routing.json5
{
  "rules": [
    {
      "event": "m5_agent_trigger",
      "conditions": [
        {
          "type": "indicator_threshold",
          "indicator": "ADX",
          "timeframe": "H1",
          "pair": "{pair}",
          "min": 20         // unter 20 = kein Trend → Event wird nicht weitergeleitet
        },
        {
          "type": "indicator_threshold",
          "indicator": "ATR_PCT",
          "timeframe": "H1",
          "pair": "{pair}",
          "min": 0.05       // zu geringer ATR = Markt schläft
        }
      ],
      "target": "OANDA_EURUSD_AA_ANLYS"
    }
  ]
}
```

**Weg B — Snapshot Stop-Switch**

Im Snapshot-Profil des AA-Agenten wird ein Stop-Switch konfiguriert. Der Snapshot-Builder prüft die Bedingung vor dem LLM-Aufruf und bricht ab wenn sie nicht erfüllt ist — ohne dass ein LLM-Token verbraucht wird.

```json5
// config/system.json5 → snapshot_profiles
"aa_regime_filtered_v1": {
  "stop_conditions": [
    {
      "indicator": "ADX",
      "timeframe": "H1",
      "operator": "less_than",
      "value": 20,
      "message": "ADX {value} < 20 — kein Trend, Zyklus übersprungen"
    },
    {
      "indicator": "CHOP",
      "timeframe": "H1",
      "operator": "greater_than",
      "value": 61.8,
      "message": "Chop Index {value} > 61.8 — seitlicher Markt"
    }
  ],
  // ... restliche Snapshot-Konfiguration
}
```

Weg B ist zu bevorzugen: er ist näher am Agenten, loggt den Skip-Grund direkt in `agent_decisions`, und der Snapshot-Profil-Name macht die Konfiguration selbstdokumentierend.

---

### 2. Account Killswitch (Equity Drawdown Stopp)

**Was VTX macht:** Wenn Equity innerhalb eines Zeitfensters (z. B. 24h) vom Hochpunkt um mehr als X% fällt, stoppt der Bot automatisch und schließt optional alle Positionen.

**In OpenForexAI:** Identisch zur bestehenden dynamischen SL-Anpassung — ein EC auf dem M5-Event prüft den Account-Status und publiziert bei Schwellwert-Überschreitung ein Stopp-Event.

```json5
// config/RunTime/event_routing.json5
{
  "rules": [
    {
      "event": "m5_candle_available",
      "handler": "equity_killswitch",
      "config": {
        "max_drawdown_pct": 5.0,          // Stopp wenn Equity 5% unter Tageshoch
        "evaluation_window_hours": 24,
        "close_positions_on_stop": true,
        "on_trigger_event": "system_killswitch_triggered"
      }
    }
  ]
}
```

```json5
// Das ausgelöste Event stoppt alle Agenten via Routing
{
  "rules": [
    {
      "event": "system_killswitch_triggered",
      "target": "*",                        // broadcast an alle Agenten
      "action": "pause"
    }
  ]
}
```

Der GA-Agent kann denselben Mechanismus für längerfristige Performance-Metriken nutzen (Max Loss Count der Woche, Min Hold Time unterschritten etc.) — analog zur aktuellen SL-Anpassungslogik, nur mit einem anderen Trigger-Threshold und einer anderen Zielaktion.

---

### 3. Behavior State + Performance im Prompt

**Was VTX macht:** Das LLM bekommt mit jedem Prompt den aktuellen Zustand seiner eigenen Performance: heutiger P&L, Drawdown seit Tageshoch, ob Guardrails aktiv sind.

**In OpenForexAI:** Das Snapshot-Profil wird um eine `performance_context`-Sektion erweitert. Die Daten kommen aus `account_status` und `order_book` (beide bereits in der DB).

```json5
// config/system.json5 → snapshot_profiles
"aa_default_v2": {
  "performance_context": {
    "enabled": true,
    "lookback_hours": 24,
    "fields": [
      "session_pnl_pct",        // P&L seit Sessionstart in %
      "trades_today",           // Anzahl Trades heute
      "losses_today",           // Anzahl Losses heute
      "drawdown_from_high_pct", // Drawdown vom Tageshoch
      "current_equity"          // Aktuelles Equity
    ]
  },
  "regime_context": {
    "enabled": true,
    "indicators": ["ADX", "CHOP", "ATR_PCT"],
    "timeframe": "H1"
  }
  // ... restliche Snapshot-Konfiguration
}
```

Das ergibt im User Prompt einen zusätzlichen Block:

```
=== Session Performance ===
Equity: 10,245 USD | Session P&L: -0.8% | Losses heute: 2 | Drawdown vom High: 1.2%

=== Markt-Regime ===
ADX (H1): 24.3 (schwacher Trend) | Chop: 48.2 (neutral) | ATR%: 0.09%
```

Das LLM weiß damit: "Ich habe heute bereits 2 Losses gemacht und bin im leichten Drawdown — in dieser Situation ist Abwarten oder kleinere Positionsgröße sinnvoller als ein aggressiver Einstieg."

---

## Zweistufige Prüfung (Review-Agent) — bereits möglich durch Config

VTX nennt es „Review Model" — einen zweiten LLM-Aufruf der jede Trade-Entscheidung prüft bevor sie ausgeführt wird.

**Konfiguration in OpenForexAI:**

```json5
// config/system.json5 → agents
"OANDA_EURUSD_AA_REVW": {
  "type": "AA",
  "llm": "anthropic_fast",          // günstigeres/schnelleres Modell für Kritik
  "broker": "oanda_practice",
  "pair": "EURUSD",
  "system_prompt": "Du bist ein kritischer Trade-Reviewer. Du erhältst eine Handelsempfehlung und prüfst sie auf: Übereinstimmung mit dem Marktkontext, Risiko/Reward-Verhältnis, ob der Entry-Zeitpunkt sinnvoll ist. Du genehmigst oder verwirfst das Signal mit Begründung. Du hast keine Trading-Tools.",
  "tool_config": {
    "allowed_tools": [],             // kein Zugriff auf place_order etc.
    "approval_mode": "direct"
  },
  "event_triggers": ["analysis_result"]
}
```

```json5
// config/RunTime/event_routing.json5
{
  "rules": [
    // AA sendet analysis_result → Review-Agent
    { "event": "analysis_result", "target": "OANDA_EURUSD_AA_REVW" },
    // Review-Agent sendet signal_approved → BA
    { "event": "signal_approved",  "target": "OANDA_ALL..._BA_TRADE" }
    // signal_rejected landet nur im Audit-Log, kein weiteres Routing
  ]
}
```

Der BA-Agent reagiert ausschließlich auf `signal_approved` — `analysis_result` wird im Routing gar nicht an ihn weitergeleitet.

---

## Echte Lücken gegenüber VTX (erfordern neue Datenquellen oder Code)

Diese Features sind in OpenForexAI noch nicht abbildbar — nicht weil die Architektur fehlt, sondern weil externe Datenquellen oder neue Implementierungen nötig sind.

### 1. News-Integration
VTX integriert einen Echtzeit-News-Feed (Benzinga) mit über 80 konfigurierbaren Kanälen direkt in die Prompts. OpenForexAI hat keine News-Datenquelle. Ein neuer Data-Adapter + Snapshot-Sektion wäre nötig.

### 2. Economic Calendar
VTX sperrt automatisch Pre-Event (z. B. 15 min vor NFP) und Post-Event (30 min danach). Für Forex ist das besonders relevant. Die EC-Architektur könnte das umsetzen, aber die Kalendar-Datenquelle fehlt noch.

### 3. Operating Schedule (Handelszeiten)
VTX erlaubt Zeitfenster zu definieren wann der Bot aktiv ist (z. B. nur London + NY Session). In OpenForexAI gibt es aktuell kein Schedule-Konzept — der Bot läuft durch oder nicht.

### 4. Screener
VTX hat einen eigenen Screener-Agenten der Kandidaten aus einer Symbol-Liste bewertet und Trading-Symbole dynamisch zuweist. OpenForexAI handelt nur auf statisch konfigurierten Paaren. Das wäre ein neuer GA-ähnlicher Agent.

### 5. UI / Chart-Interface
VTX hat eine vollständige TradingView-Oberfläche mit Positionen, Orders, Funding History. OpenForexAI hat Management-API + Monitoring-CLI. Kein Blocker für den Betrieb, aber ein Komfort-Gap.

### 6. TWAP
VTX unterstützt TWAP-Orders nativ. OpenForexAI hat MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP — kein TWAP.

---

## Prompt-Erkenntnisse aus VTX

### System Prompt Struktur

VTX verwendet eine klare Dreiteilung die sich direkt übertragen lässt:

```
[Persona / Rolle]
Du bist ein autonomer AI-Trader. Dein Ziel ist profitable Handelsentscheidungen
auf Basis von Marktdaten zu treffen.

[Behavioral Constraints — handlungsanleitend, nicht nur deskriptiv]
- Handle nur wenn der erwartete Move die Round-Trip-Fees klar übersteigt.
- Skaliere per DCA in bestätigte Trendstrukturen; nicht in fallende Messer oder
  undefiniertes Chop. Lass Trades sich entwickeln.
- Risiko-Management ist primär. Dein Ziel ist Kapitalerhalt, dann Wachstum.

[Hard Constraints — nicht verhandelbar]
1. Du musst Risiko und Kontostand verantwortlich managen.
```

Wichtig: „Skaliere in bestätigte Trendstrukturen" ist eine konkrete Verhaltensregel, keine vage Empfehlung. Dieser Stil ist für LLMs effektiver als abstrakte Prinzipien.

### User Prompt Variablen — Referenz für Snapshot-Profile

| VTX Variable | Status in OpenForexAI | Umsetzung |
|---|---|---|
| `{current_time}` | vorhanden | Standard |
| `{candles}` | vorhanden | via Snapshot / `get_candles` |
| `{market_stats}` | vorhanden | ATR, RSI, EMA via Indikatoren |
| `{account_status}` | vorhanden | via `get_account_status` |
| `{positions}` | vorhanden | via `get_open_positions` |
| `{behavior_state}` | **Config** | Snapshot `performance_context` erweitern |
| `{performance}` | **Config** | Snapshot `performance_context` erweitern |
| `{market_regime}` | **Config** | Snapshot `regime_context` erweitern |
| `{news}` | fehlt (Datenquelle) | neuer News-Adapter nötig |
| `{calendar}` | fehlt (Datenquelle) | neuer Calendar-Adapter nötig |
| `{guidance}` | vorhanden | GA publiziert `prompt_updated` Events |

### Temperature
VTX default: 1.0 — für Trading zu hoch, erhöht Variance ohne Edge. OpenForexAI ist mit 0.1 bereits korrekt aufgestellt.

---

## Prioritäten-Matrix

| Feature | Aufwand | Impact | Typ |
|---|---|---|---|
| Review-Agent (zweistufig) | Minimal | Hoch | **Nur Config** |
| Market Regime Filter (EC / Snapshot) | Minimal | Hoch | **Nur Config** |
| Account Killswitch (EC auf M5) | Minimal | Hoch (Risk) | **Nur Config** |
| `{behavior_state}` + `{performance}` im Prompt | Gering | Hoch | **Snapshot erweitern** |
| Operating Schedule | Gering | Mittel | Code (neu) |
| Economic Calendar Lock | Mittel | Hoch (Forex!) | Code + Datenquelle |
| News-Integration | Hoch | Mittel | Code + Datenquelle |
| Screener-Agent | Hoch | Mittel | Code (neu) |
| Chart-UI | Sehr hoch | Komfort | Optional |

---

## Fazit

OpenForexAI ist architektonisch deutlich reifer als VTX Macro. Die drei Features die VTX als zentrales Unterscheidungsmerkmal vermarktet — Regime Detection, Killswitch, und Performance-Context im Prompt — sind in OpenForexAI keine Architektur-Lücken, sondern Konfigurationsaufgaben. Der Event-Bus mit EC-Filtern und der Snapshot-Stop-Switch decken diese Fälle bereits vollständig ab.

Die echten Lücken sind externe Datenquellen (News, Economic Calendar) und Komfort-Features (UI, TWAP). Für den seriösen Betrieb ist der Economic Calendar die wichtigste davon — ein ungefilteter NFP-Trade kann eine ganze Session-Performance zunichtemachen.
