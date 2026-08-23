# Demo/Testdaten vom 2026-08-23 — EA-Agent-Demonstration

Dieses Dokument hält fest, welche synthetischen (nicht-echten) Daten während der Live-Demonstration
des neuen Examiner-Agenten (EA) in der laufenden Produktionsdatenbank erzeugt wurden, bevor sie
wieder entfernt wurden. Erzeugt über das Debug-Tool `seed_demo_order` (`openforexai/tools/system/seed_demo_order.py`)
via `/tools/execute` — niemals über einen echten Broker, keine reale Order wurde je platziert.

## Zweck

Test des kompletten Ablaufs: Order geschlossen → `POSITION_CLOSED`-Event → Examiner-Agent
(`OXS_T-ALL___-EA-EXAM`) wacht auf → untersucht die Order mit echten Tools → prüft das
semantische Gedächtnis auf bereits existierende Lektionen → entscheidet, ob eine neue Lektion
gespeichert wird.

## Synthetische Order-Book-Einträge (4x, `order_book_entries`-Tabelle, SQLite)

Alle vier sind identisch aufgebaut (gleiches Szenario, mehrfach ausgelöst um verschiedene Bugs im
Trigger-Pfad zu diagnostizieren) — Pair EURUSD, BUY, Entry 1.1000, Close 1.0950, -50 Pips, Grund
"SL_HIT", zugeordnet dem (deaktivierten) Analyse-Agenten `OXS_T-EURUSD-AA-ANLYS`.

| Entry-ID | Erzeugt (UTC) | Kontext |
|---|---|---|
| `669311c1-7cf1-4d21-b82e-49f87a637a15` | 2026-08-23T04:18:17Z | Erster Testlauf — EA noch nicht aktiviert |
| `3bf0ed52-8a55-439c-b560-075be98353d9` | 2026-08-23T04:24:39Z | Nach Aktivierung von EA, vor dem Routing-Fix |
| `2c120654-692c-4715-905e-f89bd5e71480` | 2026-08-23T04:29:42Z | Nach Routing-Fix + AgentId-Fix — **hier lief die volle Untersuchung erfolgreich durch** |
| `b2adf164-584e-4672-a1e2-a6f8d1bb09b3` | 2026-08-23T04:33:02Z | Nach dem Broker-Namens-Fix (finaler Testlauf) |

Vollständiger Datensatz (identisch für alle vier, nur `id`/Zeitstempel unterscheiden sich):

```json
{
  "broker_name": "OXS_T",
  "pair": "EURUSD",
  "direction": "BUY",
  "order_type": "MARKET",
  "units": 1000,
  "requested_price": "1.1",
  "fill_price": "1.1",
  "status": "CLOSED",
  "agent_id": "OXS_T-EURUSD-AA-ANLYS",
  "entry_reasoning": "H1 showed a clean bullish breakout above resistance with strong M15 continuation candles; RSI confirmed momentum, no hard blockers.",
  "signal_confidence": 0.78,
  "market_context_snapshot": {"demo": true, "note": "Synthetic data seeded by seed_demo_order."},
  "close_reason": "SL_HIT",
  "close_price": "1.095",
  "close_reasoning": "Demo close seeded by seed_demo_order for testing the Examiner agent.",
  "pnl_pips": "-50.000"
}
```

## Semantischer Speicher-Eintrag (1x, LanceDB-Tabelle `mem_agent_OXS_T-EURUSD-AA-ANLYS`)

Manuell über das echte `semantic_memory`-Tool geschrieben (mit den echten, live gewährten
Rechten des EA-Agenten), um den Schreibpfad end-to-end zu belegen, nachdem die autonome
Untersuchung selbst entschieden hatte, keine Lektion zu speichern (kein Widerspruch zu einer
existierenden Notiz gefunden, laut eigenem Urteil nicht "distinktiv" genug).

| Feld | Wert |
|---|---|
| id | `768b524e-5d89-4859-a6aa-62ee0d8780b6` |
| Tabelle | `mem_agent_OXS_T-EURUSD-AA-ANLYS` |
| Text | "EURUSD BUY closed at -50 pips despite entry reasoning citing a clean H1 breakout with M15 continuation and RSI confirmation. No hard blockers were flagged, yet price reversed sharply. Worth watching for false-breakout risk on this setup type going forward." |
| Tags | `["demo", "post_mortem", "breakout_failure"]` |
| Importance | 0.7 |
| Broker | OXS_T |
| Erzeugt | 2026-08-23T04:36:55Z |

Erfolgreich per semantischer Suche wiedergefunden (als BA-Agent, mit dessen echten Leserechten,
Anfrage "false breakout despite bullish confirmation" → Treffer, Score 0.36).

## Im Zuge der Demo gefundene und behobene echte Bugs

1. `EA` fehlte in `AgentId._VALID_TYPES` (`openforexai/messaging/agent_id.py`) — jede Stelle, die
   Agent-IDs parst, hielt EAs eigene ID für ungültig.
2. Fehlende Routing-Regel für `position_closed` mit Sender `SYSTM-ALL___-GA-REPO` (die bestehende
   Regel erwartete einen anderen, noch nicht implementierten Sender) — Event wurde ohne Fehler
   verworfen (`config/RunTime/event_routing.json5`, neue Regel `position_closed_to_ea`).
3. Broker-Namens-Inkonsistenz: `{broker}`-Platzhalter in `forced_arguments` löst zum Modul-Schlüssel
   auf (`mt5_oxs_t`), während echte Order-Daten den Broker-Kurznamen verwenden (`OXS_T`) — Config
   auf den literalen Kurznamen umgestellt.
4. Agent-Config-Wizard-Validierung kannte `semantic_memory`s versteckte ACL-Parameter
   (`write_tables`/`read_tables`) nicht — jetzt im Tool-Schema deklariert (aber weiterhin von
   `execute()` ignoriert, falls vom LLM gesetzt — Sicherheit unverändert).

## Bereinigung

Alle oben genannten Einträge wurden nach Erstellung dieses Dokuments aus der Datenbank entfernt
(siehe Commit-/Session-Historie). Dieses Dokument ist die einzige verbleibende Aufzeichnung.
