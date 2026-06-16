[Zurück zum UI-Handbuch](ui.de.md)

# Monitor — Handbuch

Der **Monitor** ist der Live-Ereignisstrom-Viewer von OpenForexAI. Er zeigt in Echtzeit jeden Vorgang, der durch den Event Bus des Systems fließt — und ist damit das primäre Werkzeug für Laufzeitbeobachtung, Fehlersuche und das Verstehen des Systemverhaltens auf jedem Detailniveau.

Der Monitor steuert nichts — er beobachtet nur. Betrachten Sie ihn als einen ständig laufenden Log-Viewer mit intelligenter Filterung, reichhaltigen Event-Metadaten und einem strukturierten Detail-Fenster für jedes interessante Ereignis.

---

## 1. Grundkonzept

### 1.1 Einmalige Subscription, Client-seitige Filterung

Die UI abonniert den **vollständigen Ereignisstrom genau einmal** über WebSocket. Alle Events fließen in einen gemeinsamen Ring-Buffer. Die Tabs, die Sie sehen, sind **Client-seitige Filter** — das Wechseln des Tabs erstellt keine neue Subscription und lädt keine Daten neu. Es ändert lediglich den Filter, der auf die gepufferten Events angewendet wird.

Das bedeutet:
- Tab-Wechsel sind sofort (kein Netzwerk-Roundtrip).
- Während Sie einen anderen Tab lesen, gehen keine Events verloren.
- Der Ring-Buffer enthält immer die letzten 1.000 Events kategorieübergreifend.

### 1.2 Ring-Buffer

Der Monitor speichert die letzten 1.000 Ereignisse im Arbeitsspeicher und zeigt davon die letzten 1.000 im UI an. Wenn der Buffer voll ist, wird das älteste Ereignis gelöscht, um Platz für das neueste zu schaffen. Dies ist das gleitende Fenster der Systemaktivität.

Praktische Auswirkungen:
- In aktiven Systemen mit mehreren Agents kann sich der Buffer innerhalb von Minuten füllen.
- Bei ruhigen Systemen oder während des Debuggings können Events stundenlang im Buffer verbleiben.
- Das Klicken auf **Clear** leert die Anzeige, beeinflusst aber nicht den Ring-Buffer — neue Events kommen weiterhin an.

### 1.3 Live-Indikator

Der **Live-Indikator** (grüner Punkt oben rechts im Monitor-Panel) zeigt den WebSocket-Verbindungsstatus:

| Zustand | Bedeutung |
|---------|-----------|
| Grüner Punkt, pulsierend | WebSocket aktiv, Events werden empfangen |
| Grauer/roter Punkt | WebSocket getrennt — es werden keine Events empfangen |

Wenn der Live-Indikator nicht grün ist: Seite neu laden oder prüfen, ob das Backend läuft.

---

## 2. Event-Zeilen-Format

Jedes Ereignis erscheint als eine einzelne Zeile in der Monitor-Tabelle. Zeilen sind nach Ereigniskategorie farbcodiert für schnelles visuelles Scannen.

### 2.1 Spalten einer Event-Zeile

| Spalte | Inhalt |
|--------|--------|
| **Zeitstempel** | HH:MM:SS.mmm — Uhrzeit des Ereignisses mit Millisekunden-Präzision |
| **Pfeil-Indikator** | Richtungsmarkierung — siehe unten |
| **Ereignis-Typ** | Der Ereignisname (z. B. `llm_request`, `m5_candle_update`) |
| **Quell-Modul** | Welche Komponente dieses Ereignis ausgelöst hat |
| **Payload-Vorschau** | Erste ~80 Zeichen des JSON-Payloads, abgeschnitten |

### 2.2 Pfeil-Indikatoren

| Pfeil | Bedeutung |
|-------|-----------|
| `<` (links, blau) | **Eingehende Daten** — Daten, die von einer externen Quelle ankommen (Broker, LLM-Antwort) |
| `>` (rechts, grün) | **Ausgehende Aktion** — Aktion oder Signal, das nach außen gesendet wird (LLM-Anfrage, Order an Broker) |
| `!` (Ausrufezeichen, rot/orange) | **Fehler oder Warnung** — etwas ist fehlgelaufen oder erfordert Aufmerksamkeit |

### 2.3 Farbcodierung nach Kategorie

Zeilen sind farbig markiert, entsprechend ihrer Ereigniskategorie:
- **LLM-Events** — violett/lila Töne
- **Tool-Events** — blau Töne
- **Broker-Events** — orange Töne
- **Data-Events** — türkis/cyan Töne
- **Core-Events** — grau/weiß
- **Bus-Events** — gelb/gold Töne
- **Agent-Events** — grün Töne
- **Entity-Events** — indigo/dunkelblau

---

## 3. Ereignis-Tabs — Alle neun erklärt

### 3.1 All Events (Alle Ereignisse)

**Filter:** Kein Filter — zeigt jedes Ereignis von jeder Komponente.

Der **All Events**-Tab ist der ungefilterte Vollstrom. Verwenden Sie ihn, wenn Sie das vollständige Bild dessen sehen möchten, was das System gerade tut, ohne auf eine bestimmte Kategorie einzuschränken.

**Am besten geeignet für:**
- Ersten Überblick über die Systemaktivität gewinnen.
- Einen vollständigen Analyse-Zyklus vom Trigger bis zum Signal beobachten.
- Unerwartete Ereignismuster identifizieren.
- Einer Ereigniskette folgen, die mehrere Kategorien umfasst.

**Vorsicht:** In aktiven Systemen mit mehreren Agents kann All Events sehr schnell scrollen. Verwenden Sie die spezifischen Tabs für fokussierte Untersuchungen.

### 3.2 LLM Events

**Filter:** `llm_request`, `llm_response`, `llm_turn_started`, `llm_turn_completed`, `llm_turn_failed`, `llm_error`

Der **LLM Events**-Tab zeigt die gesamte Kommunikation mit dem LLM-Dienst.

#### llm_request

Wird ausgelöst, wenn ein Agent eine Anfrage an das LLM über den Event Bus sendet. Das Ereignis wird an das LLMService-Modul weitergeleitet (z. B. `llm:azure_azmin`).

Payload enthält:
- `agent_id` — welcher Agent die Anfrage initiiert hat
- `prompt_length` — ungefähre Größe des Prompts in Tokens
- `model` — welches LLM-Modell angesprochen wird
- `request_id` — eindeutige Kennung für diese Anfrage

#### llm_response

Wird ausgelöst, wenn der LLMService eine vollständige Antwort vom LLM-Anbieter empfangen hat und diese zurück an den anfragenden Agent sendet.

Payload enthält:
- `agent_id` — welcher Agent die Antwort empfängt
- `input_tokens` — verbrauchte Tokens für den Prompt
- `output_tokens` — Tokens in der Antwort
- `latency_ms` — Gesamtdauer des LLM-Aufrufs in Millisekunden
- `decision` — extrahiertes Entscheidungs-Objekt (wenn Parsing erfolgreich)
- `request_id` — entspricht dem ursprünglichen `llm_request`

#### llm_turn_started

Wird zu Beginn eines LLM-Turns innerhalb eines Agent-Zyklus ausgelöst. Nützlich für Timing: Dieses Ereignis markiert, wann der Agent tatsächlich anfängt, auf eine LLM-Antwort zu warten.

#### llm_turn_completed

Wird ausgelöst, wenn ein LLM-Turn erfolgreich abgeschlossen wurde. Bildet mit `llm_turn_started` ein Paar für die Dauermessung.

#### llm_turn_failed

Wird ausgelöst, wenn ein LLM-Turn fehlschlägt — Timeout, API-Fehler, Netzwerkfehler oder Parsing-Fehler. Payload enthält:
- `reason` — den Fehlergrund
- `error_code` — HTTP-Status oder Fehlerkategorie
- `retry_count` — wie viele Wiederholungsversuche unternommen wurden

#### llm_error

Generisches LLM-Fehlerereignis für Fehler, die außerhalb eines spezifischen Turns auftreten (z. B. Verbindungsfehler, Authentifizierungsfehler).

**LLM Events-Tab am besten geeignet für:**
- Diagnose von LLM-Verbindungsproblemen.
- Überprüfen des Token-Verbrauchs pro Agent-Zyklus.
- Verifizieren, dass Anfragen gesendet und Antworten empfangen werden.
- Untersuchen der LLM-Latenz (Zeitstempel in `llm_response`).
- Prüfen, ob das Entscheidungs-Parsing erfolgreich ist oder fehlschlägt.

### 3.3 Tool Events

**Filter:** `tool_call_started`, `tool_call_completed`, `tool_call_failed`

Der **Tool Events**-Tab verfolgt alle Tool-Aufrufe, die vom ToolDispatcher während Agent-Zyklen ausgeführt werden.

#### tool_call_started

Wird unmittelbar vor der Ausführung einer Tool-Funktion ausgelöst.

Payload enthält:
- `tool_name` — welches Tool aufgerufen wird (z. B. `get_candles`, `calculate_indicator`)
- `agent_id` — welcher Agent den Tool-Aufruf initiiert hat
- `parameters` — die übergebenen Eingabeparameter
- `call_id` — eindeutige Kennung für diesen Aufruf

#### tool_call_completed

Wird nach einer erfolgreichen Tool-Ausführung ausgelöst.

Payload enthält:
- `tool_name`
- `agent_id`
- `call_id`
- `duration_ms` — Ausführungszeit in Millisekunden
- `result_summary` — kurze Beschreibung des Ergebnisses

#### tool_call_failed

Wird ausgelöst, wenn eine Tool-Ausführung fehlschlägt.

Payload enthält:
- `tool_name`
- `agent_id`
- `call_id`
- `error` — Fehlerbeschreibung
- `duration_ms`

**Tool Events-Tab am besten geeignet für:**
- Verifizieren, dass alle Tool-Aufrufe während eines Zyklus erfolgreich abgeschlossen wurden.
- Langsame Tools identifizieren, die die Zyklusdauer erhöhen.
- Fehlerhafte Tool-Aufrufe diagnostizieren, die leere oder unvollständige Snapshots verursachen könnten.
- Verstehen, welche Tools ein Agent in welcher Reihenfolge aufruft.

### 3.4 Broker Events

**Filter:** Broker-Konnektivität, HTTP-Traffic, Sync-Events, Kontostatus-Events

Der **Broker Events**-Tab zeigt alle Interaktionen zwischen OpenForexAI und den verbundenen Broker-Adaptern.

#### broker_connected

Wird ausgelöst, wenn ein Broker-Adapter erfolgreich eine Verbindung herstellt. Payload enthält die Broker-Modul-ID und Kontodetails.

#### broker_disconnected

Wird ausgelöst, wenn eine Broker-Verbindung verloren geht. Payload enthält den Grund, falls bekannt.

#### broker_reconnecting

Wird ausgelöst, wenn der Broker-Adapter einen automatischen Wiederverbindungsversuch startet. Payload enthält die Versuchsnummer und Wartezeit.

#### broker_http_request

Wird für jede HTTP-Anfrage ausgelöst, die an die Broker-API gesendet wird. Payload enthält:
- `method` (GET/POST/PUT/PATCH)
- `endpoint` — der API-Endpunkt
- `broker_id` — welches Broker-Modul
- `body` (bei POST/PUT-Anfragen)

#### broker_http_response

Wird für jede HTTP-Antwort der Broker-API ausgelöst. Payload enthält:
- `status_code` — HTTP-Status (200, 400, 401, 500 usw.)
- `broker_id`
- `response_time_ms` — Dauer des API-Aufrufs
- `body_summary` — partieller Antwort-Body

#### sync_check_started

Wird ausgelöst, wenn ein BA-Agent einen Sync-Check beginnt — Überprüfung, ob lokal gespeicherte Positionen mit dem übereinstimmen, was der Broker als offen hat.

#### sync_check_completed

Wird ausgelöst, wenn der Sync-Check abgeschlossen ist. Wenn eine Diskrepanz gefunden wurde:
- `sync_detected: true` — eine Position wurde beim Broker als geschlossen gefunden, war lokal aber noch offen
- `position_id` — welche Position
- `action_taken` — was OpenForexAI unternommen hat

**Broker Events-Tab am besten geeignet für:**
- Diagnose von Broker-Verbindungsproblemen.
- Beobachten von API-Aufrufen für eine bestimmte Trade-Ausführung.
- Verifizieren, dass Sync-Checks laufen und abgeschlossen werden.
- Untersuchen von 4xx/5xx HTTP-Fehlern der Broker-API.

### 3.5 Data Events

**Filter:** Kerzen-Pipeline-Events, Indikator-Berechnungs-Events

Der **Data Events**-Tab zeigt den Fluss von Marktdaten durch das System.

#### m5_candle_update

Wird jedes Mal ausgelöst, wenn eine neue M5-Kerze vom Broker-Kerzen-Polling-Dienst empfangen wird. Dies ist der primäre System-Herzschlag — alle Agent-Trigger entstammen diesem Event.

Payload enthält:
- `pair` — welches Währungspaar
- `broker_id`
- `candle` — die neuen Kerzendaten (Zeitstempel, Open, High, Low, Close, Volume)
- `is_new` — ob dies eine neu geschlossene Kerze oder ein partielles Update ist

#### m5_candle_saved

Wird ausgelöst, nachdem eine neue M5-Kerze in der Datenbank gespeichert wurde.

#### candles_request

Wird ausgelöst, wenn ein Agent oder Tool Kerzen-Daten anfordert (z. B. während des Snapshot-Aufbaus).

#### candles_response

Wird ausgelöst, wenn die Kerzen-Daten-Anfrage erfüllt wurde.

#### indicator_request

Wird ausgelöst, wenn eine Indikator-Berechnung angefordert wird.

#### indicator_response

Wird ausgelöst, wenn die Indikator-Berechnung abgeschlossen ist.

**Data Events-Tab am besten geeignet für:**
- Verifizieren, dass M5-Kerzen konsistent ankommen (System-Herzschlag-Check).
- Prüfen, ob Kerzen in der Datenbank gespeichert werden.
- Diagnosieren von Datenlücken oder fehlenden Kerzen.
- Beobachten von Indikator-Berechnungen während Agent-Zyklen.

### 3.6 Core Events

**Filter:** Agent-Trigger-Events, Snapshot-Build-Events, Agent-Backlog-Events

Der **Core Events**-Tab zeigt den Lebenszyklus von Agent-Zyklen — vom Trigger bis zum Signal.

#### agent_trigger_received

Wird ausgelöst, wenn die Trigger-Bedingung eines Agents erfüllt ist und ein Zyklus beginnt. Dies ist der Startpunkt jedes Analyse-Zyklus.

Payload enthält:
- `agent_id`
- `trigger_type` — was den Agent ausgelöst hat (z. B. `m5_candle`)
- `pair`
- `candle_timestamp` — die Kerze, die diesen Zyklus ausgelöst hat

#### agent_trigger_skipped

Wird ausgelöst, wenn ein Trigger empfangen wurde, der Agent aber keinen Zyklus gestartet hat. **Dies ist das Schlüsselereignis zum Debuggen, warum ein Agent nicht läuft.**

Payload enthält:
- `agent_id`
- `reason` — warum der Trigger übersprungen wurde. Mögliche Werte:
  - `"session_filter"` — aktuelle Uhrzeit liegt außerhalb der konfigurierten Handelssession des Agents
  - `"any_candle_divider"` — der Agent ist so konfiguriert, dass er nur jede N-te Kerze läuft, und dies war nicht die N-te
  - `"runtime_paused"` — das System befindet sich im Suspend-Modus
  - `"already_running"` — ein vorheriger Zyklus ist noch nicht abgeschlossen
  - `"disabled"` — der Agent ist in der Konfiguration deaktiviert

#### agent_backlog_detected

Wird ausgelöst, wenn die Trigger-Warteschlange eines Agents mehr unverarbeitete Trigger enthält als ein konfigurierter Schwellenwert. Dies zeigt an, dass der Agent hinterherhinkt.

Payload enthält:
- `agent_id`
- `backlog_size` — Anzahl der ausstehenden Trigger
- `oldest_pending_ms` — wie alt der älteste ausstehende Trigger ist

#### agent_input_built

Wird ausgelöst, wenn der vollständige Agent-Input (Snapshot) zusammengestellt wurde und bereit ist, an das LLM gesendet zu werden. Dies markiert das Ende der Datenbeschaffungsphase.

Payload enthält:
- `agent_id`
- `snapshot_size_bytes` — Größe des zusammengestellten Snapshots
- `build_duration_ms` — wie lange der Snapshot-Aufbau gedauert hat

#### agent_decision_snapshot_built

Wird ausgelöst, wenn der Decision-Snapshot (strukturierter Output) erfolgreich aus der LLM-Antwort aufgebaut wurde.

#### agent_decision_snapshot_invalid

Wird ausgelöst, wenn die LLM-Antwort nicht in einen gültigen Decision-Snapshot geparst werden konnte. Das LLM hat etwas zurückgegeben, das nicht der erwarteten JSON-Struktur entspricht.

Payload enthält:
- `agent_id`
- `reason` — warum die Validierung fehlschlug
- `raw_response_preview` — erste 200 Zeichen der rohen LLM-Antwort

**Core Events-Tab am besten geeignet für:**
- Bestätigen, dass Agents wie erwartet getriggert werden.
- Herausfinden, warum ein Agent nicht läuft (Prüfen von `agent_trigger_skipped` und dessen `reason`-Feld).
- Beobachten des Snapshot-Aufbauprozesses.
- Identifizieren von LLM-Antwort-Parsing-Fehlern.

### 3.7 Bus Events

**Filter:** Alle Event-Bus-Routing-Events

Der **Bus Events**-Tab zeigt jede Nachricht, die durch den internen Event Bus geroutet wird, mit vollständigen Sender- und Ziel-Informationen.

Bus Events sind die Infrastruktur-Schicht: jede `llm_request`, jedes Signal, jeder Trigger und jede Antwort wird über den Bus geroutet, und Bus Events zeigt die Routing-Metadaten.

Jede Bus-Event-Zeile enthält:
- `sender` — der Agent oder das Modul, das die Nachricht gesendet hat (z. B. `agent:OXS_T-EURUSD-AA-ANLYS`)
- `target` — der beabsichtigte Empfänger (z. B. `llm:azure_azmin`, `agent:OXS_T-EURUSD-BA-TRADE`)
- `event_type` — der Typ der gerouteten Nachricht
- `routing_rule` — welche Routing-Regel gematcht hat (falls zutreffend)

**Bus Events-Tab am besten geeignet für:**
- Verifizieren, dass Signale korrekt von AA- zu BA-Agents geroutet werden.
- Beobachten der vollständigen LLM-Aufrufkette (Anfrage von Agent → LLMService → Antwort zurück zum Agent).
- Diagnosieren von Routing-Fehlkonfigurationen, bei denen Signale ihre Ziele nicht erreichen.
- Verstehen des Nachrichtenflusses zwischen Systemkomponenten.

### 3.8 Agent Events

**Filter:** Agent-Entscheidungs- und Signal-Events

Der **Agent Events**-Tab zeigt Events im Zusammenhang mit der Entscheidungsfindung und Signalgenerierung von Agents.

#### agent_decision_made

Wird ausgelöst, wenn ein Agent eine Handelsentscheidung getroffen hat. Dies ist das primäre Output-Ereignis eines AA-Analyse-Zyklus.

Payload enthält:
- `agent_id`
- `decision` — BUY, SELL oder HOLD
- `confidence` — 0–100
- `entry`, `stop_loss`, `take_profit`
- `reasoning_summary` — kurzer Text aus der LLM-Antwort
- `entry_quality`

#### agent_signal_generated

Wird ausgelöst, wenn ein Signal (BUY oder SELL) generiert und an den BA-Agent gesendet wird. HOLD-Entscheidungen erzeugen kein Signal.

Payload enthält:
- `agent_id` (AA-Agent)
- `target_agent_id` (BA-Agent, der das Signal empfängt)
- `signal_type` — BUY oder SELL
- `signal_id` — eindeutige Kennung für dieses Signal

**Agent Events-Tab am besten geeignet für:**
- Bestätigen, dass AA-Agents Entscheidungen generieren.
- Verifizieren, dass BUY/SELL-Signale an BA-Agents gesendet werden.
- Überwachen von Konfidenz-Levels und Entscheidungstypen über Zeit.
- Prüfen, ob der Agent konsistent HOLD wählt (was bedeutet, dass keine Trades platziert werden).

### 3.9 Entity Events

**Filter:** EntityController (EC) Run-Events

Der **Entity Events**-Tab zeigt den Lebenszyklus von EntityController-Runs — den strukturierten Ausführungseinheiten, die Signale verarbeiten und den Trade-Zustand verwalten.

#### ec_run_started

Wird ausgelöst, wenn ein EntityController-Run beginnt. Dies passiert, wenn der BA-Agent ein Signal empfängt und beginnt, es zu verarbeiten.

#### ec_run_completed

Wird ausgelöst, wenn ein EC-Run erfolgreich abgeschlossen wird.

Payload enthält:
- `ec_id`
- `agent_id`
- `duration_ms`
- `output_summary` — kurze Beschreibung, was der EC-Run produziert hat

#### ec_run_failed

Wird ausgelöst, wenn ein EC-Run fehlschlägt. Payload enthält den Fehlergrund.

#### ec_run_output

Wird für den spezifischen Output eines EC-Runs ausgelöst. Payload enthält:
- `output_type` — `order_placed`, `order_rejected`, `position_update` usw.
- `details` — spezifische Details des Outputs

**Entity Events-Tab am besten geeignet für:**
- Verifizieren, dass BA-Agent-Signale verarbeitet werden.
- Diagnostizieren, warum ein Trade ausgeführt wurde oder nicht.
- Beobachten der vollständigen Ausführungskette für ein bestimmtes Signal.

---

## 4. Doppelklick — Event-Detail-Fenster

Ein Doppelklick auf eine Event-Zeile öffnet das **Event-Detail-Fenster** — ein schwebendes, ziehbares und in der Größe veränderbares Fenster, das die vollständigen Event-Daten mit Kontext zeigt.

### 4.1 Fenster-Layout

#### Titelleiste

Die Titelleiste zeigt:
- **Ereignis-Typ** — den vollständigen Event-Namen (z. B. `llm_response`)
- **Zeitstempel** — HH:MM:SS.mmm
- **Broker/Pair** — falls auf dieses Ereignis zutreffend
- **Kopieren-Button** — kopiert das vollständige JSON-Payload in die Zwischenablage
- **Schließen-Button** — schließt das Fenster (auch: **Escape**-Taste)

#### Kontext-Leiste

Die Kontext-Leiste befindet sich zwischen der Titelleiste und dem JSON-Payload. Sie bietet menschenlesbare Kontextinformationen für das Ereignis:

| Feld | Inhalt |
|------|--------|
| **Was** | Klartextbeschreibung, was dieser Ereignis-Typ bedeutet |
| **Warum** | Warum dieses Ereignis ausgelöst wurde und was es als Nächstes triggert oder signalisiert |
| **Quelle** | Das `source_module`-Feld — welche Komponente dieses Ereignis erzeugt hat (z. B. `agent:OXS_T-EURUSD-AA-ANLYS`, `broker.OXS_T`, `eventbus`) |
| **Sender** | Die Bus-Sender-Agent-ID (wenn über Event Bus geroutet) |
| **Ziel** | Die Bus-Ziel-Agent-ID (wenn dieses Ereignis an einen bestimmten Agent gerichtet war) |
| **Broker/Pair** | Das Broker-Modul und Währungspaar, falls relevant |

Die Kontext-Leiste verwandelt rohe technische Events in verständliche Informationen — Sie müssen nicht jeden Event-Namen auswendig kennen. Die Felder **Was** und **Warum** erklären jeden Ereignis-Typ in klarem Deutsch.

#### JSON-Payload

Das vollständige Event-Payload wird als **formatiertes JSON** angezeigt:
- Alle Felder sind aufgeklappt (keine kollabierten Objekte)
- `\n`-Escape-Sequenzen werden als echte Zeilenumbrüche gerendert
- `\"`-Escape-Sequenzen werden als echte Anführungszeichen gerendert
- Lange Strings werden nicht abgeschnitten — das vollständige Payload wird immer angezeigt
- Verwenden Sie den **Kopieren-Button** in der Titelleiste, um das gesamte Payload zu kopieren

### 4.2 Ziehen und Größe ändern

Das Detail-Fenster ist:
- **Ziehbar** — Klicken und Ziehen der Titelleiste zum Verschieben
- **In der Größe veränderbar** — Ziehen eines beliebigen Randes oder einer Ecke zum Vergrößern/Verkleinern

Dies ermöglicht es, das Detail-Fenster neben der Ereignisliste zu positionieren, um weiterhin Events zu scannen während Sie die Details lesen.

### 4.3 Selektierte Zeile bleibt markiert (dunkelorange)

Nachdem Sie das Detail-Fenster schließen, bleibt die Zeile, die Sie doppelgeklickt haben, **dunkelorange markiert** in der Ereignisliste. Dies erleichtert das Wiederfinden des inspektierten Events, auch wenn viele neue Events eingetroffen sind.

Die Markierung bleibt bestehen, bis Sie eine andere Zeile anklicken oder sie explizit löschen.

### 4.4 Tastaturkürzel

Drücken Sie **Escape**, um das Detail-Fenster ohne Maus zu schließen.

---

## 5. Steuerung

### 5.1 Clear-Button

Der **Clear**-Button leert die aktuelle Anzeige. Der Ring-Buffer empfängt weiterhin neue Events, und neue Events erscheinen sofort nach dem Löschen. Clear ist nützlich, um eine saubere Ansicht zu bekommen, bevor eine bestimmte Aktion ausgelöst wird, die beobachtet werden soll.

**Hinweis:** Clear betrifft nur die Anzeige. Der 10.000-Events-Ring-Buffer wird nicht zurückgesetzt — er sammelt weiterhin Events. Wenn Sie nach dem Löschen einen anderen Tab öffnen, sehen Sie die alten Events nicht mehr.

### 5.2 Live-Indikator

Der Live-Indikator zeigt den WebSocket-Verbindungsstatus. Wenn er nicht grün ist:
1. Prüfen Sie, ob das Backend läuft (Initial-Seite — System-Status).
2. Seite neu laden.
3. Wenn das Backend läuft und der Indikator grau bleibt: Browser-Konsole auf WebSocket-Verbindungsfehler prüfen.

---

## 6. LLM-Architektur-Hinweis: Event-Bus-Durchlauf (seit v0.7)

Seit Version 0.7 laufen **alle LLM-Aufrufe über den Event Bus**. Dies ist eine wichtige Architekturänderung, die die vollständige LLM-Aufrufkette im Monitor sichtbar macht.

### 6.1 Die vollständige LLM-Aufrufkette

```
Agent-Analyse-Zyklus
  → Snapshot aufgebaut (agent_input_built)
  → llm_request an Event Bus gesendet
  → Event Bus routet zu LLMService (llm:azure_azmin)
  → LLMService: llm_turn_started
  → LLMService ruft Azure OpenAI API auf (HTTP)
  → Azure OpenAI API antwortet
  → LLMService: llm_turn_completed
  → LLMService sendet llm_response an Event Bus
  → Event Bus routet Antwort zurück zum originierenden Agent
  → Agent verarbeitet LLM-Antwort
  → agent_decision_made ausgelöst
```

### 6.2 Wo jeder Schritt im Monitor sichtbar ist

| Schritt | Tab | Ereignis |
|---------|-----|---------|
| Snapshot zusammengestellt | Core Events | `agent_input_built` |
| LLM-Anfrage von Agent gesendet | Bus Events | `llm_request` (Sender = Agent, Ziel = llm:...) |
| LLM-Turn beginnt | LLM Events | `llm_turn_started` |
| LLM-Turn endet | LLM Events | `llm_turn_completed` |
| LLM-Antwort zurückgeroutet | Bus Events | `llm_response` (Sender = llm:..., Ziel = Agent) |
| Entscheidung extrahiert | Agent Events | `agent_decision_made` |

Das bedeutet: Sie können den **vollständigen Hin- und Rückweg** eines LLM-Aufrufs vollständig im Monitor verfolgen, ohne Server-Logs prüfen zu müssen.

---

## 7. Praktische Debug-Workflows

### 7.1 Vollständigen EURUSD-Analyse-Zyklus beobachten

Ziel: Einen kompletten Analyse-Zyklus vom M5-Trigger bis zum Handelssignal beobachten.

1. Monitor öffnen. Auf **All Events**-Tab wechseln.
2. **Clear** klicken, um sauber zu starten.
3. Auf die nächste M5-Kerze warten (sichtbar in Data Events oder All Events als `m5_candle_update`).
4. Folgende Sequenz beobachten:
   - `m5_candle_update` (Pair: EUR_USD)
   - `agent_trigger_received` (Agent: OXS_T-EURUSD-AA-ANLYS)
   - Tool-Aufrufe: `candles_request` / `candles_response` für mehrere Timeframes
   - `agent_input_built` — Snapshot bereit
   - `llm_request` in Bus Events — an LLM gesendet
   - `llm_turn_started` in LLM Events
   - `llm_turn_completed` in LLM Events
   - `llm_response` in Bus Events — zurück zum Agent
   - `agent_decision_made` in Agent Events
   - (Bei BUY/SELL:) `agent_signal_generated` → `ec_run_started` → `ec_run_completed`
5. `agent_decision_made` doppelklicken, um die vollständige Entscheidung im Detail-Fenster zu sehen.

### 7.2 Herausfinden, warum ein Agent nicht läuft

Ziel: Den Grund finden, warum keine Agent-Zyklen stattfinden.

1. Monitor öffnen. Auf **Core Events**-Tab wechseln.
2. 5–10 Minuten warten (mindestens ein M5-Kerzen-Intervall).
3. Nach `agent_trigger_skipped`-Events für den betreffenden Agent suchen.
4. Das Ereignis doppelklicken, um das Detail-Fenster zu öffnen.
5. Das **`reason`**-Feld im Payload lesen:
   - `"session_filter"` → Agent liegt außerhalb seiner konfigurierten Handelssession. Session-Konfiguration prüfen.
   - `"any_candle_divider"` → Agent ist so konfiguriert, dass er nur jede N-te Kerze läuft, und dies war nicht die N-te.
   - `"runtime_paused"` → System ist pausiert. Continue auf der Initial-Seite klicken.
   - `"already_running"` → Vorheriger Zyklus ist noch nicht abgeschlossen (langsames LLM oder viele Tools).
   - `"disabled"` → Agent ist in der Konfiguration deaktiviert. `system.json5` prüfen.
6. Wenn es kein `agent_trigger_skipped`-Event gibt: **Data Events**-Tab auf `m5_candle_update` für dieses Pair prüfen. Kommen überhaupt Kerzen an?

### 7.3 LLM-Aufrufe und Token-Verbrauch prüfen

Ziel: Bestätigen, dass LLM-Aufrufe funktionieren, und den Token-Verbrauch überprüfen.

1. Auf **LLM Events**-Tab wechseln.
2. Einen Execute-Lauf im Agent Chat starten (oder auf einen natürlichen Zyklus warten).
3. Nach `llm_turn_started` gefolgt von `llm_turn_completed` Ausschau halten.
4. `llm_response` doppelklicken, um das Detail-Fenster zu sehen.
5. Im Payload prüfen:
   - `input_tokens` und `output_tokens` — Gesamt-Token-Verbrauch
   - `latency_ms` — wie lange der LLM-Aufruf gedauert hat
   - `decision` — wurde die Entscheidung erfolgreich extrahiert?
6. Falls stattdessen `llm_turn_failed` erscheint: `reason`-Feld auf den Fehler prüfen.

### 7.4 Broker-Verbindung überwachen

Ziel: Sicherstellen, dass der Broker verbunden ist und korrekt antwortet.

1. Auf **Broker Events**-Tab wechseln.
2. Nach `broker_connected` suchen (sollte beim System-Start erschienen sein).
3. `broker_http_request` / `broker_http_response`-Paare beobachten — diese entstehen beim Kerzen-Polling und bei Sync-Checks.
4. In `broker_http_response`: das `status_code`-Feld prüfen.
   - `200` — alles in Ordnung
   - `4xx` — Authentifizierungs- oder Parameter-Fehler
   - `5xx` — Server-seitiger Broker-Fehler
5. Wenn `broker_disconnected` gefolgt von `broker_reconnecting` erscheint: Das System versucht automatische Wiederherstellung. Auf `broker_connected` warten, um Erfolg zu bestätigen.

### 7.5 Routing debuggen

Ziel: Verifizieren, dass Signale korrekt von AA- zu BA-Agents geroutet werden.

1. Auf **Bus Events**-Tab wechseln.
2. Einen Execute-Lauf im Agent Chat für den AA-Agent starten.
3. Nach `agent_signal_generated` im Bus-Ereignisstrom Ausschau halten.
4. Ereignis doppelklicken. In der Kontext-Leiste:
   - **Sender** sollte die AA-Agent-ID sein.
   - **Ziel** sollte die BA-Agent-ID sein.
5. Falls das Ziel falsch oder fehlend ist: Event-Routing-Konfiguration unter Config → Event Routing prüfen.
6. Nach dem Signal: in **Entity Events** auf `ec_run_started` warten, um zu bestätigen, dass der BA-Agent es empfangen hat.

### 7.6 Abgelehnten Trade untersuchen

Ziel: Herausfinden, warum ein Trade abgelehnt wurde.

1. Auf **Entity Events**-Tab wechseln.
2. Nach `ec_run_output` mit `output_type: "order_rejected"` suchen.
3. Ereignis doppelklicken. Das `details`-Feld im Payload erklärt den Ablehnungsgrund:
   - Risikolimit überschritten
   - Duplikat-Signal erkannt
   - Broker-API-Ablehnung (mit Status-Code)
   - Ungültige SL/TP-Werte
4. Auch **Broker Events** auf `broker_http_response` um denselben Zeitstempel prüfen — wenn der Broker die Order abgelehnt hat, zeigt die HTTP-Antwort einen 4xx-Status mit Fehlermeldung.

---

## 8. Tipps für effektive Monitor-Nutzung

**Den richtigen Tab verwenden:** All Events ist in einem aktiven System überwältigend. Verwenden Sie die spezifischen Tabs für Untersuchungen eines bestimmten Bereichs. Nur für kategorienübergreifende Sequenzen auf All Events zurückgreifen.

**Vor dem Triggern löschen:** Wenn Sie eine bestimmte Aktion beobachten möchten (z. B. einen Execute-Lauf), zuerst die Anzeige löschen, dann die Aktion auslösen. Das ergibt einen sauberen, fokussierten Ereignisstrom.

**Großzügig doppelklicken:** Die Kontext-Leiste im Detail-Fenster erklärt jeden Ereignis-Typ in klarem Deutsch. Auch wenn Sie einen Event-Namen nicht kennen — ein Doppelklick verrät Ihnen, was er bedeutet.

**Detail-Fenster offen lassen:** Das Detail-Fenster wird nicht automatisch aktualisiert. Sie können es offen lassen, während neue Events eintreffen — es bleibt auf dem Event fixiert, den Sie geöffnet haben. Die dunkelorange Markierung der selektierten Zeile stellt sicher, dass Sie es wiederfinden.

**Ring-Buffer füllt sich schnell:** In aktiven Systemen können sich 10.000 Events innerhalb weniger Minuten ansammeln. Für lange Debug-Sessions den relevantesten Tab regelmäßig prüfen, anstatt weit zurückzuscrollen.

**Mit Agent Chat kombinieren:** Für tiefste Einblicke führen Sie einen Execute-Zyklus im Agent Chat durch, während Sie gleichzeitig die LLM Events- und Core Events-Tabs im Monitor beobachten. Sie sehen den Snapshot-Aufbau (Core Events) und die LLM-Verarbeitung (LLM Events) in Echtzeit, während das Execute-Ergebnis im Chat-Panel erscheint.
