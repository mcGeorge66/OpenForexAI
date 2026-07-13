# Bus-Architektur: Event Bus & Monitoring Bus

## Übersicht

Das System hat zwei vollständig getrennte Busse mit unterschiedlichen Aufgaben:

| | Event Bus | Monitoring Bus |
|---|---|---|
| **Zweck** | Kommunikation zwischen Systemteilen | Beobachtung des Systems |
| **Richtung** | Bidirektional (Anfrage + Antwort) | Nur eingehend (fire-and-forget) |
| **Empfänger** | Registrierte Mitglieder mit Queue | Abonnenten (z.B. WebSocket-Clients) |
| **Fehlerfall** | Nachricht wird gedroppt + gewarnt | Still gedroppt, System läuft weiter |
| **Payload** | Python-Objekte (kein JSON-Zwang) | Immer vollständig im DEBUG-Modus |

---

## Event Bus

### Aufgabe

Alle Kommunikation zwischen Systemteilen läuft ausschließlich über den Event Bus. Kein Modul darf ein anderes direkt aufrufen. Jedes Modul registriert sich beim Start als **Mitglied** und bekommt eine persönliche Queue. Nachrichten landen in dieser Queue und werden von dort verarbeitet.

### Nachrichtenformat

Jede Nachricht (`AgentMessage`) enthält:

```
id              → eindeutige UUID der Nachricht
event_type      → Art des Events (z.B. "repo_request")
source_agent_id → Absender (z.B. "OXS_T-EURUSD-AD-ADPT")
target_agent_id → Empfänger, oder null wenn Routing-Tabelle entscheidet
payload         → dict mit den eigentlichen Daten
correlation_id  → Rückbezug auf eine Anfrage (nur bei Antworten gesetzt)
```

### Zustellmethoden

Der Event Bus kennt drei Methoden, die in dieser Reihenfolge geprüft werden:

---

#### 1. Rückantwort (Request-Response)

**Wann:** Die Nachricht hat eine `correlation_id`, die einer wartenden Anfrage entspricht.

**Wie es funktioniert:**
- Modul A schickt eine Anfrage auf den Bus und registriert dabei seinen `msg.id` als Schlüssel für eine Antwort
- Modul B verarbeitet die Anfrage und schickt eine Antwort mit `correlation_id = msg.id` des Anfragers zurück
- Der Bus erkennt die `correlation_id`, löst die wartende Anfrage direkt auf — ohne Routing
- Die Antwort landet direkt im Code von Modul A (wie ein Funktionsrückgabewert)

**Wichtig:** Die Routing-Tabelle wird übersprungen. Die Antwort geht nie in eine Queue.

**Beispiel:** `repo_request` → `repo_response`, `candles_request` → `candles_response`

---

#### 2. Direkte Zustellung (Direct Target)

**Wann:** Die Nachricht hat eine `target_agent_id`, aber keine passende `correlation_id`.

**Wie es funktioniert:**
- Die Nachricht geht direkt in die Queue des genannten Empfängers
- Die Routing-Tabelle wird übersprungen
- Ist der Empfänger nicht registriert, wird die Nachricht still gedroppt

**Beispiel:** `positions_request` von BA-ANLYS → `OXS_T-EURUSD-AD-ADPT`

---

#### 3. Regelbasierte Zustellung (Routing-Tabelle)

**Wann:** Die Nachricht hat keine `target_agent_id`.

**Wie es funktioniert:**
- Die Routing-Tabelle wird anhand von `event_type` und `source_agent_id` ausgewertet
- Die erste passende Regel bestimmt den/die Empfänger
- Passt keine Regel: Nachricht wird gedroppt + Warnung ins Monitoring
- Mehrere Regeln können passen — höchste Priorität gewinnt

**Empfänger-Platzhalter in Regeln:**
- `*` → beliebiger Wert
- `{sender.broker}` → Broker-Präfix des Absenders (z.B. `OXS_T`)
- `{sender.pair}` → Pair des Absenders (z.B. `EURUSD`)

---

### Mitglieder-IDs (Namensschema)

IDs folgen dem Schema: `BROKER-PAIR__-TYP-NAME`

| Segment | Länge | Beispiel |
|---|---|---|
| Broker | 5 Zeichen | `OXS_T`, `SYSTM`, `GLOBL` |
| Pair | 6 Zeichen | `EURUSD`, `ALL___` |
| Typ | 2 Zeichen | `AA`, `BA`, `EC`, `GA`, `AD` |
| Name | variabel | `ANLYS`, `RELAY`, `REPO` |

---

### Alle registrierten Mitglieder

| ID | Name | Beschreibung |
|---|---|---|
| `SYSTM-ALL___-GA-REPO` | RepositoryService | Alle Datenbankzugriffe |
| `SYSTM-ALL___-GA-DATA` | DataContainer | Kerzendaten, Indikatorberechnungen |
| `SYSTM-ALL___-GA-CFGSV` | ConfigService | Konfigurationen für Agenten und ECs |
| `{B}-{P}-AD-ADPT` | Broker Adapter | MT5-Kommunikation (pro Pair) |
| `{B}-{P}-AA-ANLYS` | Asset Analyst | Marktanalyse (pro Broker+Pair) |
| `{B}-{P}-EC-RELAY` | EC Relay | Verarbeitet AA-Signale, leitet an BA weiter |
| `{B}-ALL___-BA-ANLYS` | Business Analyst | Handelsentscheidungen, Orderausführung |
| `GLOBL-ALL___-GA-*` | Global Agents | Spezialisierte globale Analysten (TA, News, etc.) |
| `llm:{name}` | LLM Service | Führt LLM-Anfragen aus |
| `GLOBL-ALL___-EC-ECHO` | Echo EC | Testkomponente |
| `MGMT_-ALL___-GA-MGMT` | Management API | REST/WS-Verwaltungsschnittstelle |

---

### Alle Events auf dem Event Bus

#### Systemdienste

| Event | Absender → Empfänger | Beschreibung |
|---|---|---|
| `repo_request` | Jeder → `SYSTM-ALL___-GA-REPO` | Datenbankoperation anfragen |
| `repo_response` | `SYSTM-ALL___-GA-REPO` → Anfragender | Ergebnis der DB-Operation (Rückantwort) |
| `agent_config_requested` | Jeder → `SYSTM-ALL___-GA-CFGSV` | Konfiguration anfragen |
| `ec_config_requested` | EC → `SYSTM-ALL___-GA-CFGSV` | EC-Konfiguration anfragen |
| `agent_config_response` | `SYSTM-ALL___-GA-CFGSV` → Agent | Konfigurationsantwort (Rückantwort) |
| `ec_config_response` | `SYSTM-ALL___-GA-CFGSV` → EC | EC-Konfigurationsantwort (Rückantwort) |
| `candles_request` | Tools/Agenten → `SYSTM-ALL___-GA-DATA` | Kerzendaten anfragen |
| `candles_response` | `SYSTM-ALL___-GA-DATA` → Anfragender | Kerzendaten (Rückantwort) |
| `llm_request` | Agenten → `llm:{name}` | LLM-Anfrage |
| `llm_response` | `llm:{name}` → Agent | LLM-Antwort (Rückantwort) |

#### Broker Adapter → System

| Event | Absender → Empfänger | Beschreibung |
|---|---|---|
| `m5_candle_update` | Adapter → `SYSTM-ALL___-GA-DATA` | Neue M5-Kerze |
| `candle_gap_detected` | Adapter → `SYSTM-ALL___-GA-DATA` | Lücke in M5-Kerzen erkannt |
| `candle_data_bulk` | Adapter → `SYSTM-ALL___-GA-DATA` | Bulk-Kerzendaten (Reparatur) |
| `account_status_updated` | Adapter → `SYSTM-ALL___-GA-DATA` | Kontostatus aktualisiert |
| `m5_agent_trigger` | Adapter → `{B}-{P}-AA-*` + Echo EC | Analyse auslösen (verzögert, nach Kerzenabschluss) |

#### Broker Adapter ↔ Broker Adapter (Direkt)

| Event | Absender → Empfänger | Beschreibung |
|---|---|---|
| `order_request` | Agent → Adapter | Order platzieren |
| `order_result` | Adapter → Agent | Ergebnis der Order (Rückantwort) |
| `position_close_request` | Agent → Adapter | Position schließen |
| `position_close_result` | Adapter → Agent | Ergebnis (Rückantwort) |
| `order_modify_request` | Agent → Adapter | Order ändern (SL/TP) |
| `order_modify_result` | Adapter → Agent | Ergebnis (Rückantwort) |
| `positions_request` | Agent → Adapter | Offene Positionen anfragen |
| `positions_response` | Adapter → Agent | Positionen (Rückantwort) |
| `account_status_request` | Agent → Adapter | Kontostatus anfragen |
| `account_status_response` | Adapter → Agent | Kontostatus (Rückantwort) |
| `candle_repair_requested` | DataContainer → Adapter | Fehlende Kerzen nachladen |

#### Analyse-Pipeline (AA → EC → BA)

| Event | Absender → Empfänger | Beschreibung |
|---|---|---|
| `signal_generated` | AA → `{B}-{P}-EC-RELAY` | Analyseergebnis mit Signal |
| `analysis_result` | AA → `{B}-{P}-EC-RELAY` | Analyseergebnis ohne Signal |
| `ec_output` | EC-RELAY → `{B}-ALL___-BA-*` | Verarbeitetes Signal für BA |
| `signal_approved` | BA → `{B}-*-AA-*` | Order genehmigt |
| `signal_rejected` | BA → `{B}-*-AA-*` | Order abgelehnt |
| `prompt_updated` | BA oder GA → alle AAs | Prompt-Update weitergeben |

#### Sync & Trading

| Event | Absender → Empfänger | Beschreibung |
|---|---|---|
| `order_book_sync_discrepancy` | Adapter → `{B}-ALL___-BA-*` | Position in MT5 geschlossen, DB-Eintrag offen |
| `order_book_close_reasoning` | Jeder → `{B}-ALL___-BA-*` | Begründung für Positionsschliessung |
| `position_closed` | Adapter → `{B}-ALL___-BA-*` | Position wurde geschlossen |
| `order_placed` | Adapter → `{B}-ALL___-BA-*` | Order-Bestätigung |
| `risk_breach` | Jeder → `{B}-ALL___-BA-*` | Risikolimit überschritten |
| `optimization_complete` | Jeder → `GLOBL-ALL___-GA-*` | Optimierungslauf abgeschlossen |
| `analysis_requested` | Jeder → `GLOBL-ALL___-GA-*` | Externe Analyse anfordern |

---

### Routing-Tabelle (aktuell konfiguriert)

Datei: `config/RunTime/event_routing.json5`

| ID | Event | Von | An | Priorität |
|---|---|---|---|---|
| `config_request_to_service` | `agent_config_requested` | `*` | `SYSTM-ALL___-GA-CFGSV` | 1 |
| `ec_config_request_to_service` | `ec_config_requested` | `*-*-EC-*` | `SYSTM-ALL___-GA-CFGSV` | 1 |
| `repo_request_to_service` | `repo_request` | `*` | `SYSTM-ALL___-GA-REPO` | 2 |
| `m5_candle_to_data` | `m5_candle_update` | `*-*-AD-ADPT` | `SYSTM-ALL___-GA-DATA` | 10 |
| `candle_gap_to_data` | `candle_gap_detected` | `*-*-AD-ADPT` | `SYSTM-ALL___-GA-DATA` | 10 |
| `candle_data_bulk_to_data` | `candle_data_bulk` | `*-*-AD-ADPT` | `SYSTM-ALL___-GA-DATA` | 10 |
| `account_status_to_data` | `account_status_updated` | `*-*-AD-ADPT` | `SYSTM-ALL___-GA-DATA` | 10 |
| `m5_agent_trigger_to_matching_aa` | `m5_agent_trigger` | `*-*-AD-ADPT` | `{sender.broker}-{sender.pair}-AA-*` | 11 |
| `m5_agent_trigger_to_echo_ec` | `m5_agent_trigger` | `*-*-AD-ADPT` | `GLOBL-ALL___-EC-ECHO` | 12 |
| `aa_signal_to_ec` | `signal_generated` | `*-*-AA-*` | `{sender.broker}-{sender.pair}-EC-RELAY` | 20 |
| `aa_analysis_to_ec` | `analysis_result` | `*-*-AA-*` | `{sender.broker}-{sender.pair}-EC-RELAY` | 20 |
| `ec_relay_to_ba` | `ec_output` | `*-*-EC-RELAY` | `{sender.broker}-ALL___-BA-*` | 20 |
| `ba_approved_to_aa` | `signal_approved` | `*-ALL___-BA-*` | `{sender.broker}-*-AA-*` | 20 |
| `ba_rejected_to_aa` | `signal_rejected` | `*-ALL___-BA-*` | `{sender.broker}-*-AA-*` | 20 |
| `ba_prompt_update_to_aa` | `prompt_updated` | `*-ALL___-BA-*` | `{sender.broker}-*-AA-*` | 20 |
| `analysis_requested_to_ga` | `analysis_requested` | `*` | `GLOBL-ALL___-GA-*` | 20 |
| `ga_prompt_broadcast` | `prompt_updated` | `GLOBL-*-GA-*` | `*-*-*-*` | 25 |
| `risk_breach_to_ba` | `risk_breach` | `*` | `{sender.broker}-ALL___-BA-*` | 25 |
| `ob_sync_to_ba` | `order_book_sync_discrepancy` | `*-*-AD-ADPT` | `{sender.broker}-ALL___-BA-*` | 30 |
| `ob_close_reasoning_to_ba` | `order_book_close_reasoning` | `*` | `{sender.broker}-ALL___-BA-*` | 30 |
| `position_closed_to_ba` | `position_closed` | `*-*-AD-ADPT` | `{sender.broker}-ALL___-BA-*` | 30 |
| `order_placed_to_ba` | `order_placed` | `*-*-AD-ADPT` | `{sender.broker}-ALL___-BA-*` | 30 |
| `optimization_complete_to_ga` | `optimization_complete` | `*` | `GLOBL-ALL___-GA-*` | 40 |

**Hinweis Priorität:** Niedrigere Zahl = höhere Priorität. Bei mehreren passenden Regeln gewinnt die mit der niedrigsten Prioritätszahl.

---

## Monitoring Bus

### Aufgabe

Der Monitoring Bus ist ein reiner Beobachtungskanal — er hat keine Auswirkung auf das System. Jedes Modul kann jederzeit ein `MonitoringEvent` senden. Ist kein Abonnent verbunden, wird das Event still verworfen.

### Unterschied zum Event Bus

- Kein Request-Response, keine Routing-Regeln, keine direkte Zustellung
- Nur Einweg: Modul → Monitoring Bus → Abonnenten
- Kein Mitglied muss sich registrieren — jeder kann senden, ohne sich anzumelden
- Fehler im Monitoring brechen nie das System

### Quellen von Monitoring-Events

Der Monitoring Bus erhält Events aus zwei Quellen:

**1. Direkte Emissionen** (gezielt nur ans Monitoring):
- Broker Adapter: `SYNC_CHECK_STARTED`, `SYNC_CHECK_COMPLETED`, `SYNC_DISCREPANCY_FOUND`, `M5_CANDLE_FETCHED`, `M5_CANDLE_QUEUED`, `BROKER_CONNECTED`, `BROKER_ERROR`, etc.
- RepositoryService: `SYSTEM_INFO` (Operation + Latenz)
- Agenten: `TOOL_CALL_STARTED`, `TOOL_CALL_COMPLETED`, `LLM_REQUEST`, `LLM_RESPONSE`, etc.
- DataContainer: `M5_CANDLE_SAVED`, `DATA_CONTAINER_ACCESS`

**2. Kopien vom Event Bus** (jede Nachricht die den Bus durchläuft):
- Im **INFO-Modus**: mit gekürztem Payload, bestimmte häufige Events unterdrückt
- Im **DEBUG-Modus**: vollständiger Payload, keine Unterdrückung, keine Kürzung

### DEBUG-Modus Anforderungen

Im DEBUG-Modus gelten folgende **verbindlichen Regeln**:

1. Jede Nachricht die den Event Bus durchläuft wird **ungekürzt** ans Monitoring weitergegeben
2. Der vollständige `payload` der Nachricht ist enthalten — keine Felder werden weggelassen
3. Keine Event-Typen werden unterdrückt oder gefiltert
4. Die Reihenfolge im Monitoring entspricht der Reihenfolge auf dem Bus

### INFO-Modus (Produktivbetrieb)

Folgende Event-Typen werden im INFO-Modus **unterdrückt** (zu häufig für sinnvolle Beobachtung):

- `account_status_updated`
- `broker_http_request` / `broker_http_response`
- `data_container_access`
- `m5_candle_fetched` / `m5_candle_queued` / `m5_candle_saved`
- `sync_check_started` / `sync_check_completed`

Alle anderen Events werden im INFO-Modus mit gekürzten Strings (max. 2.000 Zeichen) und Listen (max. 20 Einträge) weitergegeben.

### Ring-Buffer

Der Monitoring Bus hält die letzten **10.000 Events** im Speicher. Neue WebSocket-Verbindungen bekommen beim Verbindungsaufbau die letzten 500 Events als Wiedergabe.

### Monitoring-Event-Format

```json
{
  "id": "uuid",
  "timestamp": "2026-06-03T20:55:14.234Z",
  "source_module": "broker.OXS_T",
  "event_type": "repo_response",
  "broker_name": null,
  "pair": null,
  "payload": { ... }
}
```

---

## Zusammenarbeit beider Busse

```
Modul A                    Event Bus                  Modul B
   │                           │                          │
   │── publish(msg) ──────────>│                          │
   │                           │── resolve_future() ─────>│  (Rückantwort)
   │                           │   oder                   │
   │                           │── queue.put(msg) ────────>│  (Direkt/Routing)
   │                           │
   │                           │── emit(copy) ────────────────────> Monitoring Bus
   │                           │   (DEBUG: mit vollem Payload)        │
   │                           │                                      │
   │                           │                               WebSocket-Clients
```

**Verbindliche Regel:** Der Monitoring Bus ist immer passiv — er verändert nie eine Nachricht auf dem Event Bus und hat keinen Einfluss auf die Zustellung.

---

## Offene Punkte / bekannte Probleme

1. **Serialisierung im RepositoryService**: `get_open_order_book_entries` gibt `OrderBookEntry` Pydantic-Objekte zurück. Der Sync-Loop erwartet Dicts und ruft `.get("broker_order_id")` auf — das schlägt auf Pydantic-Objekten still fehl. Alle Repo-Ergebnisse mit Pydantic-Modellen müssen vor dem Eintragen in den Response-Payload serialisiert werden (`model_dump(mode="json")`).

2. **Sync-Loop funktionslos**: Durch Problem #1 ist der `_sync_loop` seit dem Anfang broken — PENDING→OPEN Übergänge und Close-Detection funktionieren nicht über den Loop.

3. **REST-Endpoint als Workaround**: Geschlossene Einträge wurden bisher über den REST-Endpoint `/orderbook` (beim UI-Aufruf) reconciliert, nicht über den Sync-Loop.
