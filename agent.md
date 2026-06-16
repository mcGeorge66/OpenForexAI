# OpenForexAI-B — Agent Onboarding

Autonomes Multi-Agent Forex-Trading-System (educational/research, Practice-Modus only).
LLMs treffen alle Handelsentscheidungen; Menschen konfigurieren nur Rules und Prompts.

---

## Pflichtregeln (immer einhalten)

| Regel | Detail |
|---|---|
| **Vor Meinung lesen** | Nie Annahmen aus dem Kontext — relevante Datei zuerst lesen |
| **Nur nach Bestätigung implementieren** | Nicht-triviale Änderungen (neue Keys, Flags, Mechanismen, Refactoring) erst beschreiben, auf Ja warten |
| **Frontend immer bauen** | Nach jeder Änderung in `ui/src/` sofort `npm run build` in `ui/` ausführen |
| **Antwortlänge anpassen** | Ja/Nein-Frage → Ja/Nein. Keine langen Erklärungen bei einfachen Fragen |
| **Kein decision_semantics-Fallback** | `calculation_blocks` ist der einzige Berechnungspfad im Snapshot-System — niemals einen Fallback einführen |

---

## Technologie

- **Python 3.11+**, async/await überall, kein blocking I/O
- **FastAPI** + Uvicorn — Management API auf Port 8765
- **SQLite** (dev) / **PostgreSQL** (prod), async Treiber
- **Logging:** `structlog.get_logger(__name__)` — niemals `logging.getLogger`
- **Config:** JSON5 mit `${VAR}` Substitution
- **Linting:** ruff, 120 Zeichen
- **Imports:** `from __future__ import annotations` am Anfang jeder Datei
- **Tests:** pytest, asyncio_mode="auto" — kein `@pytest.mark.asyncio` nötig
- **UI:** React + Tailwind in `ui/` — muss nach Änderungen gebaut werden

---

## Dateistruktur (wichtigste Pfade)

```
openforexai/
├── main.py / bootstrap.py          # Einstiegspunkt + Verdrahtung
├── agents/
│   ├── agent.py                    # Einzige Agent-Klasse (AA/BA alle gleich)
│   └── analysis_snapshot.py        # Snapshot-Builder (parallel, kein LLM)
├── messaging/
│   ├── bus.py                      # EventBus (async pub/sub)
│   └── routing.py                  # RoutingTable aus event_routing.json5
├── tools/                          # 11 Tools: market, account, trading, system
├── adapters/llm/                   # Anthropic, OpenAI, Azure, LMStudio, Ollama
└── adapters/brokers/               # OANDA, MetaTrader 5

config/
├── system.json5                    # EINZIGE Konfigurationsquelle
└── RunTime/
    ├── event_routing.json5         # Routing-Regeln (hot-reloadbar)
    └── agent_tools.json5           # Tool-Freigaben per Agent

ui/src/                             # React-Frontend
```

---

## Agent-System

**Agent-ID Format:** `[BROKER(5)]_[PAIR(6)]_[TYPE(2)]_[NAME(1-5)]`
Beispiel: `OXS_T-EURUSD-AA-ANLYS`, `OXS_T-ALL___-BA-ANLYS`

**Einen neuen Agent hinzufügen = nur Eintrag in `config/system.json5` — kein Code.**

**Wichtige Agent-Felder:**
```json5
"OXS_T-USDJPY-AA-ANLYS": {
  "type": "AA",
  "llm": "<llm_module_name>",
  "broker": "<broker_module_name>",
  "pair": "USDJPY",
  "AnyCandle": 3,                   // Analysiert jede 3. M5-Kerze
  "session_filter": [{"session": "tokyo", "pre": 15, "post": -30}],
  "snapshot_profile": "aa_default_v1",
  "system_prompt": "...",
  "tool_config": {"allowed_tools": [], "max_tokens": 4096}
}
```

---

## Wie Agents funktionieren

```
M5-Kerze abgeschlossen (Broker-Adapter, +60s Verzögerung)
  → m5_agent_trigger Event auf EventBus
  → Agent empfängt Trigger
  → _should_run_for_trigger() prüft AnyCandle-Divider (Counter)
  → _is_session_allowed() prüft Session-Filter (Candle-Timestamp, nicht Systemzeit!)
  → build_analysis_snapshot() — 13 Tool-Calls parallel via asyncio.gather()
  → LLM-Call (~1-2 Minuten)
  → analysis_result Event → EC-RELAY → BA-Agent
```

**Counter-Reset-Bug (bekannt, teilweise gefixt):** Der Candle-Counter wird in
`_should_run_for_trigger()` zurückgesetzt bevor Session-Filter und Lock geprüft
werden. Fix in `agent.py`: Bei `should_run=True` aber `session_allowed=False`
wird Counter auf `divider-1` zurückgesetzt (statt 0), damit der nächste Trigger
sofort neu versucht.

**CheckNextCandle:** Hardcoded `_early_trigger_enabled = True`. Wenn das LLM
`"CheckNextCandle": true` zurückgibt, wird `_m5_candle_event_count = any_candle_divider`
gesetzt → nächste Kerze triggert sofort.

---

## Snapshot-System

- Snapshot wird in `analysis_snapshot.py` durch `build_analysis_snapshot()` erstellt
- **13 Tool-Blocks** feuern **parallel** via `asyncio.gather()` — dauert <3 Sekunden
- Danach laufen `calculation_blocks` (pure Python, kein I/O, kein LLM)
- **Kein Fallback:** `calculation_blocks` ist der einzige Pfad — kein `decision_semantics`

---

## Event-Routing

Regeln in `config/RunTime/event_routing.json5` — hot-reloadbar via `POST /routing/reload`.

```json5
{
  "rules": [{
    "id": "unique_id",
    "description": "Beschreibung",
    "comment": "Persönliche Notizen",    // neu, kein Routing-Effekt
    "event": "m5_agent_trigger",
    "from": "*",
    "to": "*-EURUSD-AA-*",
    "priority": 100,
    "disable": false
  }]
}
```

`to`-Targets: Literal-ID, Template `{sender.pair}`, Wildcard-Pattern `*-EURUSD-*`, `"*"` (Broadcast)

---

## Laufende Architektur-Umstellung (Stand: 2026-06-02)

**Plan:** Vollständige Umstellung auf Event-Bus als einzigen Kommunikationskanal.
Plan-Dokument: `C:\Users\zentr\.claude\plans\aufgabe-neues-modul-valiant-fountain.md`

**Kernentscheidungen (bereits genehmigt):**
- `subscribe()` / `@handlers` werden vollständig entfernt
- `register_agent()` → `register_member()` (Bus-Mitglied, nicht nur Agents)
- Pending-Futures-Mechanismus im Bus für Response-Matching
- `RepositoryService` (`SYSTM-ALL___-GA-REPO`) — neues Bus-Mitglied für DB-Zugriff
- `DataContainer` (`SYSTM-ALL___-GA-DATA`) — vollwertiges Bus-Mitglied mit `run()`
- Broker-Adapter: bidirektional, `run()` ersetzt `start_background_tasks()`
- `ToolContext` verliert direkte `broker`/`data_container`/`repository`-Referenzen

**14 Implementierungsschritte (Reihenfolge):**
EventBus → EventTypes → RepositoryService → DataContainer → Broker Adapter
→ Tools → ToolContext → ToolDispatcher → Agent Bridge → Management API
→ Bootstrap → MonitoringBus → Routing-Tabelle → UI Eventflow

---

## Offene Aufgabe: Swing Levels Date Anchor

Swing-Level-Lookback soll an den Timestamp der ältesten Chart-Kerze gebunden werden
statt an berechnete Kerzenanzahl. Neuer Parameter `from_time` für `get_swing_levels`.
**Vor Implementierung mit User abstimmen** — noch nicht genehmigt.

---

## Management API (Port 8765)

```
GET  /health              System-Status
GET  /agents              Alle Agents mit Queue-Tiefen
GET  /routing/rules       Aktive Routing-Regeln
POST /routing/reload      event_routing.json5 hot-reload
POST /events              Event manuell injizieren
GET  /monitoring/events   Ring-Buffer (1000 Events)
GET  /docs                Swagger UI
```

---

## Monitoring CLI

```bash
python tools/monitor.py                        # Alle Events live
python tools/monitor.py --filter llm_response  # Nach Typ filtern
python tools/monitor.py --pair EURUSD          # Nach Pair filtern
```
