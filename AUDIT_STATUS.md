# OpenForexAI — Audit- & Fix-Status (Handoff)

**Stand:** 2026-07-06 · **Nächster Schritt:** auf Freigabe warten — Scope/Reihenfolge noch **nicht** entschieden. Es wurde **noch kein Code geändert.**

## Auftrag (Original)
Gesamte Anwendung untersuchen und **sofort** beheben: Bugs, Race Conditions, Legacy-/toter/doppelter/falscher Code, Inkonsistenzen (gleiche Rückgabe = gleiche Datentypen), **keine Kompatibilitäts-Krücken** mehr. Ziel: absolut fehlerfreier, verlässlicher Code. Symptom laut Owner: seltene, schwer auffindbare Fehler, die erst nach Wochen als finanzieller Schaden auffallen (keine Abstürze, „Zufallstreffer"). Sicherung des Codes existiert → Arbeit ohne Rückfrage erlaubt (Scope-Entscheidung bei 642 Funden trotzdem eingeholt).

## Was erledigt ist
- **Exhaustiver Audit abgeschlossen** (Workflow, 824 Agenten, adversarial verifiziert). Ergebnis vollständig in **`AUDIT_FINDINGS.json`** (642 Einträge, je mit `severity, category, file, line, title, impact, fix, related_files`).
- **Test-Baseline erhoben** (venv: `.venv/Scripts/python.exe -m pytest`): **21 failed, 39 passed, 14 errors**. Ursachen überwiegend **veraltete Tests / unvollständige Mocks**, nicht neue Prod-Bugs:
  - `tests/conftest.py` → `MockRepository` fehlt `save_ec_run` (Interface gewachsen) → 14 errors.
  - `tests/unit/test_analysis_snapshot.py` → nutzt entferntes `data_container`-Kwarg an `build_analysis_snapshot`/`ToolContext`/`preview_snapshot_tool_block`.
  - `tests/unit/test_runtime_tool_config.py` → ruft entferntes `ConfigService.resolve_runtime_tool_config`.
  - `tests/unit/test_broker_base.py` → `EventBus.subscribe` existiert nicht mehr.
  - `test_azure_llm_transcript.py` / `test_llm_debug_diagnostics.py` → umgehen `__init__`, daher `_reasoning_effort` fehlt (Test-Setup-Problem, `azure.py:101` setzt es korrekt).
  - `test_order_book_*` / `test_sub_prompts` → veraltete Architektur (ToolContext-Signatur, MockBroker-Methoden).

## Statistik der Funde
- **Aktueller Stand nach Batch 1: 628 offen — 3 kritisch, 48 hoch, 204 mittel, 373 niedrig.** (14 gelöste Findings ausgelagert nach `AUDIT_FINDINGS_RESOLVED.json`.)
- Ursprünglich (Audit-Lauf): **14 kritisch, 51 hoch, 204 mittel, 373 niedrig**
- Kategorien: 236 bug · 115 inconsistency · 101 dead_code · 62 duplicate · 49 compat_shim · 42 race · 37 suboptimal
- 48 Roh-Funde wurden bei der Verifikation als **falsch verworfen** (nicht in der Datei).

## Kritische Funde (14) — erklären die „stille Verluste nach Wochen"
| Kat. | Ort | Kurz |
|---|---|---|
| bug | `openforexai/management/api.py:3898` | Routing-Hot-Reload ruft nicht existierende `load_rules_from_file` → geänderte Routing-Regeln werden nie aktiv (Fehler wird verschluckt). Verletzt CLAUDE.md-Kernprinzip. Fix: `_routing_table.load(cfg_path)` bzw. `await _bus.reload_routing()`. |
| bug | `openforexai/adapters/brokers/oanda.py:380` | `place_order` liefert **orderID**, `get_open_positions` liefert **tradeID** → matchen nie im Sync-Loop → Positionen werden still nicht wiedergefunden. |
| bug | `openforexai/adapters/brokers/oanda.py:317` | `sync_key` als `clientExtensions` statt `tradeClientExtensions` gesendet → landet nie am Trade → sync_key-Matching tot auf OANDA. |
| bug | `openforexai/adapters/brokers/oanda.py:367` | Nicht-idempotente Order in blindem `retry_async` → **Doppel-Orders** bei Timeout nach Broker-Annahme. |
| bug | `openforexai/adapters/brokers/base.py:233` | `_handle_close_request` stringifiziert `TradeResult`, hardcodet `success=True` → Close-Status/pnl/close_price erreichen Agent/Orderbook nie. |
| bug | `openforexai/adapters/brokers/base.py:257` | `_handle_modify_request` stringifiziert `TradeResult` → **broker-abgelehnte SL/TP als „angewendet" verbucht**. |
| bug | `openforexai/tools/trading/modify_order.py:55` | `ORDER_MODIFY_REQUEST` ohne Pflichtfeld `entry_id` → Bus-Validierung **lehnt jede SL/TP-Änderung ab**. |
| bug/incons. | `openforexai/tools/trading/close_position.py:65,73,101` | Batch/Notfall-Close liest `position_id`, Producer sendet `broker_position_id` → leere IDs + mögliche Endlos-Rekursion; **Kill-Switch (`position_id='0'`) zielt auf nie registrierten Adapter** → still verworfen. |
| bug | `openforexai/agents/analysis_snapshot.py:624` | Calc-Block-Fehler landen nicht im errors-Channel → Fehler-Dict wird als Ergebnis eingebettet, Zyklus läuft weiter. |
| suboptimal | `openforexai/tools/news/get_news.py:122` | Blockierende `requests`-Calls im async-Loop → friert das ganze System für bis zu Minuten ein. |
| bug | `scripts/initial_setup.py:391` | `_write_system_config` überschreibt die ganze `system.json5` mit Modul-Stub → zerstört agents/snapshot_profiles/event_composers. |

## Hohe Funde (51) — Auszug (voll in AUDIT_FINDINGS.json, `severity=high`)
- `utils/time_utils.py:28,45` — `detect_session()` kennt kein „closed", `is_market_open()` gibt **nie False** (Wochenende/Feiertag ignoriert).
- `data/container.py:563` — unvollständiger letzter Resample-Bucket (M15…D1) wird als fertige Kerze geliefert → verfälscht Indikatoren.
- `data/indicators.py:176` — `synthetic_dxy` richtet Komponenten per Head-Index statt Zeitstempel aus.
- `oanda.py:259` / `container.py:633` — `Candle.spread` in **drei verschiedenen Einheiten** je Broker gespeichert.
- `agent.py:170,477` — `stop()` flippt nur `_running` (ein voller Trade-Zyklus feuert noch); Timer- und Query-getriggerte Zyklen umgehen `_run_lock` → **parallele Zyklen**.
- `composers/composer.py:217` — kein per-Zyklus-Exception-Guard → eine Exception killt den ganzen EC-Loop.
- `adapters/database/postgresql.py:95,276` + `adapters/data/postgresql.py:63` — PG-Schema fehlen Spalten/Tabellen (`decision_type_new`, `reasoning`, `market_snapshot`, `ec_runs`, `assessment_memory`) → **PostgreSQL-Backend divergiert von SQLite**.
- `management/api.py:1055` (`OrderStatus` nicht importiert → NameError killt Reconciliation), `:4507` (Path-Traversal in SPA-Catch-all), `:3790` (laufende ECs bekommen kein Config-Update nach `PUT /config/system`).
- LLM-Adapter: `openai.py:199/231`, `azure.py:658` — uneinheitliche Tool-Message-Konvertierung & unsichtbare Output-Truncation (`finish_reason='length'` nicht gemappt).
- UI: `KbEditor.tsx:294` & `SearchPanel.tsx:60` — **XSS** (rehypeRaw + identity urlTransform; `dangerouslySetInnerHTML` auf ungespeicherten FTS-Snippets); `AgentConfigWizard.tsx:253` — Save backt aufgelöste Platzhalter dauerhaft in `forced_arguments`.

## ✅ Erledigt — Batch 1 (2026-07-06): die 8 freigegebenen kritischen Fixes
Alle kompilieren; Testsuite unverändert (21f/39p/14e — vorbestehende veraltete Tests, kein neuer Schaden); Standalone-Checks grün.

1. **`api.py`** — `load_rules_from_file` → `_routing_table.load(cfg_path)` an **beiden** Call-Sites (Save-Endpoint + Config-Import). Import-Pfad wirft jetzt bei Reload-Fehler HTTP 500 statt `except: pass`.
2. **`base.py` `_handle_close_request`** — nutzt jetzt `model_dump(mode="json")` (3-Branch wie `_handle_order_request`), kein `str()`/`success=True`-Hardcode mehr; Fehler wird geloggt.
3. **`base.py` `_handle_modify_request`** — dito `model_dump`; zusätzlich `entry_id` aus Request-Payload in die Response gespiegelt (Pflichtfeld `order_modify_result`).
4. **`modify_order.py`** — Order-Book-Lookup vor den Request gezogen, `entry_id` in `ORDER_MODIFY_REQUEST`-Payload (Pflichtfeld) → Bus lehnt nicht mehr jede SL/TP-Änderung ab.
5. **`close_position.py`** — Batch/Notfall lesen jetzt `broker_position_id` (statt nie vorhandenem `position_id`) + Leer-ID-Guard gegen Rekursion; Notfall-Close (`'0'`) routet auf registrierten Adapter (`context.pair`) statt nicht existierendem `ALL___`, mit klarer Fehlermeldung wenn kein Pair-Kontext.
6. **`analysis_snapshot.py`** — `_calc_script` schluckt Exceptions nicht mehr; `_execute_calculation_blocks` gibt `(calculations, errors)` zurück, fehlgeschlagene Blöcke → `None` + Fehler im Snapshot-`errors`-Channel.
7. **`get_news.py`** — blockierende `find_event_ids`/`create_events_markdown`/`read_text` via `asyncio.to_thread` ausgelagert → Event-Loop friert nicht mehr ein.
8. **`scripts/initial_setup.py`** — `_write_system_config` merged jetzt in bestehende `system.json5` (agents/snapshot_profiles/event_composers bleiben erhalten); Voll-Stub nur bei fehlender Datei; Parse-Fehler → Abbruch statt Überschreiben.

**Vollständigkeits-Abgleich gegen `fix`/`impact`/`related_files` jedes Findings (nachgezogen):**
- `api.py`-Finding `related_files` nannte **CLAUDE.md** → Tabelle auf `RoutingTable.load(cfg_path)` aktualisiert.
- `base.py:233`-Finding `fix` verlangte **Feld-Mapping** → `close_position.py` liest jetzt `fill_price`→close_price, `broker_order_id`→order_id, `pnl` aus dem serialisierten `TradeResult` (vorher lieferten diese immer `None`). Standalone verifiziert.
- `analysis_snapshot`-Finding `related_files` nannte **agent.py** → verifiziert: `agent.py:835` wertet `snapshot_errors` aus und macht `return` (kein Trade bei kaputtem Snapshot). Kette vollständig, fail-closed bestätigt.
- `initial_setup.py`-Finding `fix` empfahl **Timestamp-Backup** → vor dem Merge-Schreiben wird `system.json5.bak-<ts>` angelegt.

## ✅ Erledigt — Batch 2 (2026-07-06): dead_code-Sweep
Auftrag: „lese AUDIT_FINDINGS.json, finde alle Einträge mit category=dead_code, fixe sie wie unter fix beschrieben, lösche den Eintrag bei Erfolg."

**54 von 101 `dead_code`-Funden behoben und nach `AUDIT_FINDINGS_RESOLVED.json` verschoben** (Stempel `batch-2 dead_code sweep`). Jeder Fund wurde vor der Änderung per Grep frisch gegen den Code verifiziert (nicht aus dem Audit-Text übernommen). Regel: wenn `fix` „löschen ODER anbinden" anbot, wurde **gelöscht** — Anbinden wäre Feature-Arbeit, kein Dead-Code-Cleanup.

Größere Löschungen: `data/indicator_tools.py`, `data/correlation.py` (+ Test), `models/analysis.py`, `models/risk.py`, `ports/data_feed.py`, `utils/retry.py`, `utils/metrics.py` komplett entfernt; `models/agent.py` (AgentContext/AgentPerformance), `models/messaging.py` (MessageEnvelope) bereinigt; `models/__init__.py` geleert (kein Aufrufer nutzte den Re-Export); `sqlite.py`+`postgresql.py`: komplette `trades`-Tabelle/Methoden entfernt (superseded by order_book_entries); `agent.py`: `_configure_llm_debug_diagnostics`-No-op-Shim + `_handle_llm_debug_diagnostic` entfernt (6 Call-Sites); `mql5_calendar_lib.py`: ungenutzte `Mql5EconomicCalendar`-Klasse (74 Zeilen) entfernt. Dutzende kleinere: ungenutzte Imports/Variablen, unreachable branches, redundante Re-Imports, `ports/broker.py` (`close_position.pair`, `get_closed_trade_result.sync_key`). Stale `__pycache__`-Verzeichnisse in `tests/` und `template/` gelöscht.

**Regressions-Check:** Vorher 21 failed/39 passed/14 errors → jetzt 21 failed/**34** passed/14 errors. Die 5 fehlenden „passed" sind exakt die Tests der gelöschten toten Module (3× `test_correlation.py`, 2× in `test_models.py`) — **kein echter Schaden**, alle Imports (inkl. vollem `bootstrap.py`) geprüft.

**Bewusst übersprungen (51 verbleibende `dead_code`-Funde in `AUDIT_FINDINGS.json`)** — Gründe:
- **Architekturentscheidung nötig:** komplettes `adapters/data`-Paket + Agent-Memory-API (#4/#7/#11), `DXYPlugin.calculate`/`_pair_closes` (#6, abstrakte Methode), Approval-Gate in `tools/base.py` (#42/#43/#44 teilweise), `_data_containers`-Alias in `plugin_registry.py` (hängt an #4/#7/#11), `fetch_latest_m5_candle`-Port-Methode (#27, hat reale Doppel-Implementierung in beiden Brokern + Template-Test).
- **Feature-Arbeit statt Löschung:** `ask_llm` fehlende images/reasoning_effort-Parameter (#41 — Fix verlangt Hinzufügen, nicht Entfernen), `prompt_version`-Wiring (#9), `CloseReason`-Mapping der Broker-Close-Gründe (#8), `TradeOrder.approved_by` echte Zuordnung (#70), `pnl_pips`-Berechnung (#73).
- **Live-Nutzerdaten/Migration:** `migrations/003_agent_memory.sql`-Spalte (#97), `pass_trigger` in `config/system.json5` (#23 — Backend/Config-Teil unangetastet, UI-Teil steht noch aus).
- **Dokumentiertes User-Tool:** `scripts/run_backtest.py` (#95 — in 3 Docs beworben, nicht einfach löschbar ohne Doku-Abstimmung).
- **Größere Einzeldatei-Reviews nicht geschafft:** `openforexai/management/api.py` (6 Funde, 4500+ Zeilen — höheres Fehlerrisiko ohne mehr Zeit), `agents/agent.py` weitere Funde (#20/#21/#22), `analysis_snapshot.py` (#0/#1, ~200 Zeilen Fallback-Cluster + `CALCULATION_HANDLERS`), UI-Dateien (#12/#13/#79/#82-#89, gehören in den separaten UI-Batch mit `npm run build`), `tests/conftest.py` `MockLLMProvider` (#91 — Risiko ohne genauere Prüfung), `template/broker/demo_broker_test.py` (#99).

## Geplante Reihenfolge (restliche Befunde, sobald freigegeben) u.a. OANDA orderID vs tradeID (`oanda.py:380`), sync_key clientExtensions (`oanda.py:317`), non-idempotenter Retry (`oanda.py:367`), `time_utils.py` market-hours, PG-Schema-Divergenz, UI-XSS, sowie alle high/medium/low.

## Geplante Reihenfolge (restliche Befunde, sobald freigegeben)
0. **Testsuite → grün** als Sicherheitsnetz (veraltete Tests reparieren; wo ein Test einen echten Bug zeigt → Code fixen).
1. **Kritisch + Hoch** im Prod-Pfad, **je mit Regressionstest** (Money-Path, Sync, Hot-Reload, Market-Hours, PG-Schema, XSS).
2. **Inkonsistenzen** (Decimal/float/str, naive/aware datetime, Enum-.value, Producer/Consumer-Payload-Keys) — eine Konvention, überall.
3. **compat_shim / dead_code / duplicate** entfernen (u.a. `TradeStatus` vs `OrderStatus`, `decision_type_new`/`decision_type` Doppelspalte, mehrfach definierte `_broker_adapter_id`).
4. **UI** fixen + `npm run build` in `ui/` (Projektregel).
5. **Endverifikation**: voller pytest grün, UI-Build sauber, adversariale Re-Review über den Diff (Fix-induzierte Regressionen).

## Wichtige Betriebshinweise für die Weiterarbeit
- **Tests immer mit venv:** `.venv/Scripts/python.exe -m pytest tests/unit tests/integration -q` (globales `python` hat kein pytest).
- **Nach Frontend-Änderungen:** `npm run build` in `ui/`.
- **Task-Liste** in dieser Session: #7 Testsuite, #8 Money-Path, #9 Konsistenz, #10 Legacy/Duplikate, #11 UI, #12 Endverifikation (#12 blockiert durch #7–#11).
- **Vor Fixes** an einem Bereich: betroffene Datei frisch lesen (Zeilennummern können sich durch vorherige Fixes verschieben).
