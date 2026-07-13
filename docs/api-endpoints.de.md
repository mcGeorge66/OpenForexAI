# API Endpoint Referenz — OpenForexAI

Alle Endpoints werden vom Management-Server (`openforexai/management/api.py`) bereitgestellt.  
Base-URL: `http://<host>:<port>` (Standard-Port konfigurierbar in system.json5).

---

## System & Health

### `GET /health`
Systemzustand prüfen.  
**Response:** `{ status, uptime_seconds, registered_agents, routing_rules, timestamp }`

---

### `GET /version`
Applikationsversion aus system.json5 lesen.  
**Response:** `{ version: string }`

---

### `GET /runtime/status`
Live-Laufzeitstatus: registrierte Agents, Routing-Regelanzahl, Uptime.  
**Response:** `{ agents: string[], routing_rules: int, uptime_seconds: float }`

---

### `GET /metrics`
Basis-Metriken: Agent-Count und Queue-Tiefen.  
**Response:** `{ registered_agents, agent_queue_depths: { agent_id: qsize }, uptime_seconds }`

---

### `GET /system/ui-settings`
UI-Einstellungen (UTC-Offset für Zeitanzeige).  
**Response:** `{ ui_utc: int, broker_candle_utc_offset_hours: int }`

---

### `GET /console/initial`
Vollständige Startup-Übersicht für die Web-Konsole: LLM-Status, Broker-Status, Agents, ECs, Versionsinfo.  
**Response:** `{ logo, llm, broker, agents, event_composers, version, timestamp }`

---

### `GET /system/update/status`
Status eines laufenden oder abgeschlossenen System-Updates.  
**Response:** Update-Status-Objekt (phase, output, error, version).

---

### `POST /system/update/start`
System-Update auf eine bestimmte Version starten.  
**Body:** `{ version?: string }` — leer = neueste Version  
**Response:** `{ status: "started", requested_version }`  
**Fehler:** 409 wenn Update bereits läuft.

---

### `POST /system/runtime/pause`
Alle Agent-Zyklen pausieren (kein Neustart, Agents bleiben registriert).  
**Response:** `{ status: "paused", runtime_paused: true }`

---

### `POST /system/runtime/resume`
Pausierte Agents wieder fortsetzen.  
**Response:** `{ status: "running", runtime_paused: false }`

---

### `POST /system/restart-now`
Systemneuststart über den Wrapper-Prozess triggern (nur wenn wrapper-Mode unterstützt).  
**Response:** `{ status: "restarting", mode, signal }` oder 409 wenn nicht unterstützt.

---

## Agents

### `GET /agents`
Alle aktivierten Agents mit Queue-Tiefen auflisten.  
**Response:** `[{ agent_id, queue_size, queue_maxsize }]`

---

### `GET /agents/{agent_id}`
Einzelnen Agent abrufen.  
**Response:** `{ agent_id, queue_size, queue_maxsize }`  
**Fehler:** 404 wenn nicht registriert.

---

### `POST /agents/{agent_id}/execute`
Agent manuell ausführen (Inspection-Modus, vollständige LLM-Antwort + Trace).  
**Body:**
```json
{
  "input_text": "optional override für User-Message",
  "snapshot_profile_override": { ... },
  "decision_prompt_profile_override": { ... }
}
```
**Response:** `AgentExecuteResponse` mit Analyse-Ergebnis, Snapshot, LLM-Trace, Tokens.

---

### `POST /agents/{agent_id}/trigger` — `202 Accepted`
M5-Candle-Trigger für einen AA-Agent manuell feuern (letzter gespeicherter Candle).  
Nur für Agents vom Typ `AA`.  
**Response:** `{ message_id, status: "queued", broker_name, pair, candle_timestamp }`

---

### `GET /agents/{agent_id}/candles`
Aktuelle Candles für einen AA-Agent abrufen.  
**Query-Params:** `timeframe` (M5/M15/M30/H1/H4/D1, default M5), `count` (1–500, default 100)  
**Response:** `[{ timestamp, open, high, low, close, tick_volume, spread }]`

---

### `POST /agents/{agent_id}/ask`
Freitextfrage an einen Agent schicken und synchron auf Antwort warten.  
**Body:**
```json
{
  "question": "What is the current EURUSD trend?",
  "timeout": 60,
  "history": [{ "role": "user", "content": "..." }, { "role": "assistant", "content": "..." }]
}
```
**Response:** `{ correlation_id, agent_id, response: string }`  
**Fehler:** 504 bei Timeout.

---

## EventComposers (EC)

### `GET /composers`
Alle laufenden EC-Entities auflisten.  
**Response:** `[{ ec_id }]`

---

### `POST /composers/{ec_id}/execute`
EC-Script manuell mit beliebigem Input ausführen (Test-Modus).  
**Body:** `{ input: { ... } }`  
**Response:** `{ ec_id, output, success, error, latency_ms }`

---

### `POST /composers/{ec_id}/trigger` — `202 Accepted`
M5-Candle-Trigger für einen EC feuern (EC muss `m5_candle_trigger` in `event_triggers` haben).  
**Response:** `{ message_id, status: "queued", broker_name, pair, candle_timestamp }`

---

## Marktdaten

### `GET /candles`
Candles für ein Pair/Timeframe abrufen (broker-unabhängig).  
**Query-Params:** `pair` (required), `timeframe` (M5/M15/M30/H1/H4/D1, default M5), `count` (1–2000, default 200), `broker_name` (optional)  
**Response:** `[{ timestamp, open, high, low, close, tick_volume, spread }]`

---

### `GET /orderbook`
Order-Book-Einträge aus der DB abrufen.  
**Query-Params:** `broker_name` (optional), `pair` (optional), `status_filter` (all/open/closed/pending, default all), `limit` (1–1000, default 200)  
**Response:** `[OrderBookEntry]` (ohne Analysis-Detail)

---

### `GET /orderbook/{entry_id}`
Einzelnen Order-Book-Eintrag mit vollständiger Analysis abrufen.  
**Response:** `OrderBookEntry` (inkl. `analysis`)

---

### `GET /orderbook/{entry_id}/candles`
Candles für den Zeitraum eines Orderbook-Eintrags abrufen (für Chart-Darstellung).  
**Query-Params:** `timeframe` (default M5), `count` (200–5000, default 2000)  
**Response:** `[{ timestamp, open, high, low, close, tick_volume, spread }]`  
Gibt einen gefensterten Ausschnitt rund um `opened_at`/`closed_at` zurück.

---

## Analysen

### `GET /analyses`
Analyse-Records aus der DB abrufen.  
**Query-Params:** `agent_id` (optional), `pair` (optional), `limit` (1–1000, default 200)  
**Response:** `[AnalysisRecord]`

---

### `GET /analyses/{record_id}`
Einzelnen Analyse-Record abrufen.  
**Response:** `AnalysisRecord`  
**Fehler:** 404 wenn nicht gefunden.

---

## Monitoring

### `GET /monitoring/events`
Aktuelle Monitoring-Events aus dem Ring-Buffer abrufen (für Polling).  
**Query-Params:** `since` (ISO-8601 UTC, optional), `limit` (1–1000, default 100)  
**Response:** `[{ id, timestamp, source, event_type, broker, pair, payload }]`

---

### `GET /monitoring/pinned`
Alle gepinnten (dauerhaft gespeicherten) Monitoring-Events abrufen.  
**Response:** `[{ id, timestamp, source, event_type, broker, pair, payload }]`

---

### `POST /monitoring/events/{event_id}/pin`
Monitoring-Event pinnen (schützt vor Ring-Buffer-Eviction).  
**Response:** `{ event_id, pinned: true }`  
**Fehler:** 404 wenn Event nicht im Buffer.

---

### `DELETE /monitoring/events/{event_id}/pin`
Pin von einem Monitoring-Event entfernen.  
**Response:** `{ event_id, pinned: false }`

---

### `WS /ws/monitoring`
WebSocket-Stream für Live-Monitoring-Events.  
Beim Connect werden die letzten 1000 Ring-Buffer-Events als History replayed.  
Heartbeat-Ping alle 30 Sekunden.  
**Query-Param:** `?filter=event_type1,event_type2` — optionaler Event-Type-Filter  
**Message-Format:**
```json
{ "id", "timestamp", "source", "event_type", "broker", "pair", "payload" }
```
Heartbeat: `{ "type": "ping" }`

---

## Routing

### `GET /routing/rules`
Alle aktiven Routing-Regeln auflisten.  
**Response:** `[{ id, description, event, from_pattern, to, priority }]`

---

### `POST /routing/reload` — `202 Accepted`
Routing-Tabelle aus `config/RunTime/event_routing.json5` hot-reloaden.  
**Response:** `{ status: "reloaded", rule_count, timestamp }`

---

## Events

### `POST /events` — `202 Accepted`
Beliebiges Event manuell in den EventBus injizieren (Test/Debug).  
**Body:**
```json
{
  "event_type": "m5_candle_trigger",
  "source_agent_id": "MGMT_-ALL___-GA-MGMT",
  "target_agent_id": null,
  "payload": { ... },
  "correlation_id": null
}
```
**Response:** `{ message_id }`  
**Fehler:** 422 bei unbekanntem `event_type`.

---

## Tools

### `GET /tools`
Alle registrierten Tools auflisten.  
**Response:** `{ tools: [{ name, description, input_schema, requires_approval }] }`

---

### `POST /tools/execute`
Einzelnes Tool direkt ausführen (Test-/Debug-Modus).  
**Body:**
```json
{
  "tool_name": "get_candles",
  "arguments": { "pair": "EURUSD", "timeframe": "M5", "count": 50 },
  "agent_id": "OXS_T-EURUSD-AA-PTJ",
  "broker_name": null,
  "pair": null,
  "llm_name": null
}
```
`agent_id` optional — wird zur Kontext-Auflösung (Broker, Pair, forced_arguments) verwendet.  
**Response:** `{ tool_name, result, is_error }`

---

## Indikatoren

### `GET /indicators`
Alle registrierten technischen Indikatoren auflisten.  
**Response:** `{ indicators: string[] }`

---

## Test & Diagnose

### `POST /test/llm/check`
Ephemere LLM-Session mit frei wählbaren Tools ausführen und vollständigen Trace zurückgeben.  
**Body:**
```json
{
  "llm_name": "azure_azmin",
  "system_prompt": "You are ...",
  "messages": [{ "role": "user", "content": "..." }],
  "enabled_tools": ["get_candles"],
  "agent_id": null,
  "broker_name": null,
  "pair": null,
  "temperature": null,
  "max_tokens": null,
  "reasoning_effort": null,
  "max_tool_turns": 8
}
```
**Response:** `{ trace: [...], final_text, stop_reason, total_tokens, unknown_tools }`

---

### `POST /scripts/validate`
Python-Script auf Syntax-Fehler prüfen (kein Execution).  
**Body:** `{ code: "python source code" }`  
**Response:** `{ valid: bool, errors: [{ line, column, message }] }`

---

### `POST /debug/log`
Debug-Nachricht vom Frontend in `logs/frontend_debug.log` schreiben.  
**Body:** `{ message: string }`  
**Response:** `{ status: "ok" }`

---

## Config — System

### `GET /config/view`
system.json5 mit maskierten Sensitivfeldern (api_key, password, …) zurückgeben.  
**Response:** Config-Dict mit `"***"` für sensitive Werte.

---

### `GET /config/system`
Rohe system.json5 für den Editor zurückgeben.  
**Response:** Config-Dict (ungemaskert).

---

### `GET /config/system/text`
Roher system.json5-Text mit Kommentaren (für Text-Editor).  
**Response:** `{ text: string, file: string }`

---

### `PUT /config/system`
system.json5 speichern und sofort anwenden.  
**Body:** Config-Dict oder JSON5-String  
**Effekt (Hot-Reload):**
- ConfigService in-memory aktualisiert
- Neu aktivierte Agents/ECs werden gestartet
- Deaktivierte Agents/ECs werden gestoppt
- Alle laufenden Agents erhalten frische Config (Prompts, Profile)

**Response:** `{ status: "saved", file, runtime_apply: { started, stopped, refresh }, composer_apply }`

---

### `GET /config/root`
Absoluten Projekt-Root-Pfad zurückgeben (für UI-interne Pfadkonstruktion).  
**Response:** `{ root: string }`

---

## Config — RunTime-Dateien

### `GET /config/files/{name}`
RunTime-Config-Datei als Dict lesen.  
**Gültige Namen:** `agent_tools`, `event_routing`  
**Response:** Config-Dict

---

### `GET /config/files/{name}/text`
RunTime-Config-Datei als Rohtext lesen (Kommentare erhalten).  
**Response:** `{ text: string }`

---

### `PUT /config/files/{name}`
RunTime-Config-Datei speichern und sofort anwenden.  
**Gültige Namen:** `agent_tools`, `event_routing`  
**Body:** Config-Dict oder JSON5-String  
**Effekt (Hot-Reload):**
- `event_routing`: Routing-Tabelle wird automatisch neu geladen (`load_rules_from_file`)
- `agent_tools`: Bridge-Tools werden aus Registry entfernt und neu registriert

**Response:** `{ status: "saved", file, routing_reloaded? | bridge_tools_reloaded? }`

---

## Config — Snapshot-Konfiguration

### `POST /config/snapshots/preview`
Vollständigen Snapshot für einen Agent live rendern (ohne LLM-Call).  
**Body:**
```json
{
  "agent_id": "OXS_T-EURUSD-AA-PTJ",
  "profile_name": "Paul_Tudor_Jones_V1",
  "profile_override": { "short_timeframe": "M15" },
  "pair_override": null
}
```
**Response:** `{ agent_id, broker_name, pair, effective_profile, snapshot, validation_errors, decision_input }`

---

### `POST /config/snapshots/tool-preview`
Einzelnen Tool-Block eines Snapshot-Profils live ausführen (für Debug).  
**Body:**
```json
{
  "agent_id": "OXS_T-EURUSD-AA-PTJ",
  "tool_block": { "tool": "get_candles", "enabled": true, ... },
  "pair_override": null,
  "short_timeframe": "M15",
  "long_timeframe": "H1"
}
```
**Response:** `{ agent_id, broker_name, pair, tool_block, raw_output, transformed_output, errors }`

---

### `POST /config/snapshots/calculation-preview`
Einzelnen Calculation-Block live auswerten (für Debug).  
**Body:**
```json
{
  "agent_id": "OXS_T-EURUSD-AA-PTJ",
  "calculation_block": { ... },
  "tool_results": { "output_key": ... },
  "strategy_aggressiveness": "BALANCED",
  "short_timeframe": "M15",
  "long_timeframe": "H1"
}
```
**Response:** `{ agent_id, calculation_block, result, errors }`

---

### `GET /config/helpers/snapshot/text`
`config/snapshot_helpers.py` als Rohtext lesen.  
**Response:** `{ text: string, file: string }`

---

### `PUT /config/helpers/snapshot`
`config/snapshot_helpers.py` speichern (mit Python-Syntax-Check).  
**Body:** Python-Quellcode als plain string  
**Response:** `{ status: "saved", file }`  
**Fehler:** 422 bei Syntax-Fehler.

---

## Config — Decision Prompt

### `POST /config/decision-prompt/test-script`
Decision-Prompt-Auswahlscript mit einem Snapshot testen.  
**Body:**
```json
{
  "script": "result = 1 if snapshot.get('bias') == 'LONG' else 2",
  "snapshot": { ... },
  "prompts": [{ "id": 1, "prompt": "...", "use_placeholders": false }]
}
```
**Response:** `{ result: int, placeholders, matched_prompt, resolved_prompt, error? }`

---

## Config — Prompt Libraries

### `GET /config/prompt-library/{scope}`
Prompt-Library lesen.  
**Gültige Scopes:** `agent`, `decision`  
**Response:** `{ prompts: [...] }`

---

### `PUT /config/prompt-library/{scope}`
Prompt-Library speichern.  
**Body:** `{ prompts: [...] }`  
**Response:** `{ status: "saved", file }`

---

## Config — Snippet Libraries

### `GET /config/snippet-library/{scope}`
Snippet-Library lesen.  
**Gültige Scopes:** `script`, `snapshot`, `decision_prompt`, `ec`  
**Response:** `{ snippets: [...] }`

---

### `PUT /config/snippet-library/{scope}`
Snippet-Library speichern.  
**Body:** `{ snippets: [...] }`  
**Response:** `{ status: "saved", file }`

---

## Config — Module (LLM / Broker)

### `GET /config/modules/{module_type}`
Namen aller konfigurierten Module eines Typs auflisten.  
**Gültige Typen:** `llm`, `broker`  
**Response:** `{ names: string[] }`

---

### `GET /config/modules/{module_type}/{name}`
Modul-Config mit maskierten Sensitivfeldern lesen.  
**Response:** Config-Dict (sensitive Felder = `"***"`)

---

### `GET /config/modules/{module_type}/{name}/raw`
Rohe Modul-Config für den Editor lesen (ungemaskert).  
**Response:** Config-Dict

---

### `GET /config/modules/{module_type}/{name}/raw_text`
Roher Modul-Config-Text mit Kommentaren.  
**Response:** `{ text: string }`

---

### `PUT /config/modules/{module_type}/{name}/raw`
Modul-Config-Datei speichern.  
**Body:** Config-Dict oder JSON5-String  
**Hinweis:** Speichert nur die Datei. Laufende LLM/Broker-Instanzen werden nicht automatisch neu initialisiert (erfordern Systemneuststart).  
**Response:** `{ status: "saved", file }`

---

## Config — Packages (Import/Export)

### `POST /config/packages/export`
Agent-Package als portables JSON5 exportieren.  
**Body:**
```json
{
  "agent_ids": ["OXS_T-EURUSD-AA-PTJ"],
  "include_agents": true,
  "include_snapshot_profiles": true,
  "include_decision_prompt_profiles": true,
  "include_bridge_tools": true,
  "include_event_routing": true,
  "include_system_config": false,
  "strict_dependencies": false
}
```
**Response:** `{ package: dict, text: string }`

---

### `POST /config/packages/validate`
Package vor dem Import validieren.  
**Body:**
```json
{
  "content": "{ ... }",
  "mapping": { "llm": {}, "broker": {} },
  "replace_existing_agents": false
}
```
**Response:** `{ ok: bool, errors: [...], warnings: [...] }`

---

### `POST /config/packages/import`
Validiertes Package importieren und live anwenden.  
**Body:**
```json
{
  "content": "{ ... }",
  "mapping": { "llm": { "source_name": "target_name" }, "broker": {} },
  "replace_existing_agents": false,
  "import_agents": true,
  "import_snapshot_profiles": true,
  "import_decision_prompt_profiles": true,
  "import_bridge_tools": true,
  "import_event_routing": true,
  "import_system_config": false
}
```
**Effekt:** Schreibt system.json5 / event_routing.json5 / agent_tools.json5, wendet alle Hot-Reload-Mechanismen an.  
**Response:** `{ status: "imported"|"invalid", runtime_apply, composer_apply, validation }`

---

## Config — Information

### `GET /config/information/readme`
`config/config.md` als Text lesen (Informations-/Readme-Seite).  
**Response:** `{ text: string }`

---

### `PUT /config/information/readme`
`config/config.md` speichern.  
**Body:** Markdown-Text als plain string  
**Response:** `{ status: "saved", file }`

---

## LLM Assistant

### `POST /llm-assistant/chat`
Frage an den konfigurierten Assistant-LLM stellen (kontextbasiert über `llm_contexts/`-Dateien).  
**Body:**
```json
{
  "context_file": "script_snapshot_calculation_context.md",
  "question": "Wie funktioniert der calculation_block?",
  "history": [{ "role": "user", "content": "..." }, { "role": "assistant", "content": "..." }],
  "script": "optional python code",
  "context_data": "optional JSON/text context (überschreibt script)"
}
```
**Response:** `{ answer: string, error?: string }`

---

### `GET /llm-contexts`
Alle verfügbaren Context-Dateien in `config/llm_contexts/` auflisten.  
**Response:** `["file1.md", "file2.md"]`

---

### `GET /llm-contexts/{filename}`
Einzelne Context-Datei lesen.  
**Response:** `{ filename, content: string }`

---

### `PUT /llm-contexts/{filename}`
Context-Datei speichern (erstellt Datei falls nicht vorhanden).  
**Body:** `{ content: string }`  
**Response:** `{ ok: true }`

---

## Statische Ressourcen / Docs

### `GET /image/{filename}`
Bild aus `docs/image/` servieren (PNG, JPG, GIF, WebP, SVG, BMP).  
Path-Traversal-geschützt.

---

### `GET /chartshots/{filename}`
Chartshot-PNG aus dem konfigurierten `chartshot.output_dir` servieren.  
**Fehler:** 400 bei ungültigem Dateinamen, 404 wenn nicht vorhanden.

---

### `DELETE /chartshots/{filename}`
Chartshot-PNG löschen (nach Preview-Anzeige durch UI genutzt).  
**Response:** `{ deleted: filename }`

---

### `GET /docs/{filename}`
Markdown-Datei aus `docs/` als Text lesen.  
**Response:** `{ text: string }`

---

### `PUT /docs/{filename}`
Markdown-Datei in `docs/` überschreiben.  
**Body:** Markdown-Text als plain string  
**Response:** `{ status: "ok", file }`

---

## Zusammenfassung — Endpoint-Zählung

| Kategorie | Anzahl |
|---|---|
| System & Health | 11 |
| Agents | 6 |
| EventComposers | 3 |
| Marktdaten | 4 |
| Analysen | 2 |
| Monitoring (HTTP) | 4 |
| Monitoring (WebSocket) | 1 |
| Routing | 2 |
| Events | 1 |
| Tools | 2 |
| Indikatoren | 1 |
| Test & Diagnose | 3 |
| Config — System | 4 |
| Config — RunTime-Dateien | 3 |
| Config — Snapshot | 5 |
| Config — Decision Prompt | 1 |
| Config — Prompt Libraries | 2 |
| Config — Snippet Libraries | 2 |
| Config — Module | 5 |
| Config — Packages | 3 |
| Config — Information | 2 |
| LLM Assistant | 3 |
| Statische Ressourcen | 5 |
| **Gesamt** | **75 HTTP + 1 WS = 76** |
