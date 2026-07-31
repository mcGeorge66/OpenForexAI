[Zurück zum UI-Handbuch](ui.de.md)

# Monitor — Handbuch

Der **Monitor** ist der Live-Ereignisstrom-Viewer von OpenForexAI. Er zeigt in Echtzeit jeden Vorgang, der durch den Event Bus des Systems fließt — das primäre Werkzeug für Laufzeitbeobachtung, Fehlersuche und das Verstehen des Systemverhaltens auf jedem Detailniveau.

Der Monitor steuert nichts — er beobachtet nur. Anders als das [Event Log](ui.action.event_log.de.md) (durchsuchbares, dauerhaftes Datenbank-Archiv) zeigt der Monitor einen **flüchtigen Live-Strom**: Sein Inhalt geht beim Neuladen der Seite verloren, dafür sieht man Events, sobald sie passieren, ohne auf eine Datenbank-Abfrage zu warten.

---

## 1. Grundkonzept

### 1.1 Eine Subscription, ein Filter Builder

Die UI abonniert den vollständigen Ereignisstrom **einmal** über WebSocket (`/ws/monitoring`) und hält die letzten **500 Events** im Speicher (Ring-Buffer). Es gibt **keine festen Kategorie-Tabs** mehr — stattdessen filtert ein einziger, frei konfigurierbarer **Filter Builder** direkt im Monitor-Panel den angezeigten Ausschnitt. Das Wechseln oder Ändern eines Filters ist rein clientseitig: kein Netzwerk-Roundtrip, keine neue Subscription, keine verlorenen Events.

### 1.2 Ring-Buffer

Der Browser hält die letzten 500 empfangenen Events im Speicher; ältere Events fallen beim Eintreffen neuer Events aus dem Puffer. Das Backend selbst führt zusätzlich einen eigenen Ring-Puffer von 1.000 Events für Polling-Zwecke, unabhängig vom WebSocket-Strom.

**Praktische Auswirkung:** In aktiven Systemen mit mehreren Agenten kann sich der Puffer innerhalb von Minuten komplett füllen und älteste Events verdrängen. Wer ein bestimmtes Event dauerhaft festhalten will, sollte es **anpinnen** (Abschnitt 5) statt sich auf den Puffer zu verlassen.

**Beispiel, wann das relevant wird:** Man beobachtet gerade `agent_trigger_skipped`-Events für einen bestimmten Agenten, wird kurz abgelenkt (Telefonat, anderer Tab), und als man zurückkommt, ist das gesuchte Event bereits aus dem 500er-Puffer herausgefallen, weil in der Zwischenzeit viele andere Agenten weitergelaufen sind. In so einem Fall hilft nur noch das dauerhafte [Event Log](ui.action.event_log.de.md) — für den nächsten Fall lohnt es sich, das nächste Auftreten sofort anzupinnen, statt es „für später" im Kopf zu behalten.

### 1.3 Live-Indikator

Oben links im Panel:

| Anzeige | Bedeutung |
|---------|-----------|
| `● Live` (grün) | WebSocket aktiv, Events werden empfangen |
| `○ Disconnected` (rot) | WebSocket getrennt — es werden keine Events empfangen |

Bei `Disconnected`: Backend-Status auf der Initial-Seite prüfen, ggf. Seite neu laden.

Daneben werden zwei Zähler angezeigt: **shown** (wie viele Events nach Filterung aktuell in der Liste stehen) und **primary** (wie viele davon eigenständige Anfrage-Events sind, ohne ihre zugehörigen Antwort-Events — siehe Abschnitt 4).

### 1.4 Auto-Scroll und Reihenfolge

Neueste Events erscheinen **oben** in der Liste (nicht unten). Der `Auto`/`Paused`-Button oben rechts steuert, ob die Liste automatisch nach oben scrollt, wenn neue Events eintreffen:

- **Auto** (grün) — die Liste scrollt bei jedem neuen Event automatisch nach oben.
- **Paused** — Auto-Scroll ist deaktiviert, z. B. weil man gerade weiter unten in der Liste liest. Zurück nach oben scrollen aktiviert Auto automatisch wieder.

**Clear** leert die aktuell im Browser gehaltene Liste (nicht das Backend) — neue Events erscheinen sofort danach wieder normal.

---

## 2. Event-Zeilen-Format

Jedes Event erscheint als eine Zeile:

| Element | Inhalt |
|---------|--------|
| **`[N]`-Button** (falls vorhanden) | Anzahl korrelierter Folge-Events (siehe Abschnitt 4); Klick klappt sie ein-/aus. |
| **Zeitstempel** | Uhrzeit mit Millisekunden-Präzision. |
| **`orphan`-Markierung** | Nur bei Antwort-Events ohne sichtbares Eltern-Event im aktuellen Puffer (siehe Abschnitt 4). |
| **Ereignis-Typ** | Farbcodiert je nach Event-Typ (z. B. LLM-Events in Blautönen, Fehler in Rot, Broker-Events in Grün/Orange). |
| **`bus`/`agent`-Badge** | Nur bei `llm_request`/`llm_response`: ob das Event vom Event-Bus-Transport oder direkt vom Agent-Monitoring stammt. |
| **Quelle** | Der auslösende Agent (z. B. `OXS_T-EURUSD-AA-ANLYS`), falls vorhanden. |
| **Broker/Pair** | In eckigen Klammern, falls zutreffend. |
| **Payload-Vorschau** | Kompakte, ereignistyp-spezifische Zusammenfassung (z. B. bei `llm_response`: Turn, Stop-Grund, Token-Anzahl, Tool-Aufrufe, Modell) statt rohem JSON. |
| **Pin-Icon** | Erscheint beim Hover; pinnt/entpinnt dieses Event (Abschnitt 5). |

Ein Doppelklick auf eine Zeile öffnet das [Event-Detail-Fenster](#6-event-detail-fenster) (Abschnitt 6).

---

## 3. Filter Builder

Der Filter Builder ersetzt die früheren festen Kategorie-Tabs durch frei kombinierbare Regeln.

### 3.1 Regeln (Rules)

Jede Regel besteht aus:

| Teil | Optionen |
|------|---------|
| **Verknüpfung** | `Start` (nur bei der ersten Regel), `AND`, `AND NOT`, `OR`, `OR NOT` |
| **Feld** | `Event Type`, `Source`, `Broker`, `Pair`, `Sender`, `Target`, `Message ID`, `Correlation ID`, `Payload Field` |
| **Operator** | `contains`, `equals`, `starts with`, `ends with`, `exists` |
| **Pfad** (nur bei `Payload Field`) | Punkt-getrennter Pfad in das Payload-JSON, z. B. `decision.confidence` |
| **Wert** | Vergleichswert (entfällt bei `exists`) |

Regeln werden **von oben nach unten** ausgewertet, in der Reihenfolge, in der sie hinzugefügt wurden — die Verknüpfung jeder Regel bezieht sich auf das bisherige Zwischenergebnis. `+ Rule` fügt eine neue Regel hinzu, `Remove` entfernt sie, `New` setzt den gesamten Filter zurück (keine Regeln = alle primären Events sichtbar).

**Beispiel:** „Alle Fehler außer für das Test-Pair GBPUSD" — zwei Regeln: `Start: Event Type contains error`, dann `AND NOT: Pair equals GBPUSD`. Ein häufiger Denkfehler ist, stattdessen `OR NOT` zu wählen — das würde das Ergebnis wieder aufweiten (jedes Event, das *nicht* GBPUSD ist, würde zusätzlich durchkommen, unabhängig vom Fehler-Kriterium), da `OR` die Regel unabhängig vom bisherigen Zwischenergebnis hinzufügt.

### 3.2 Include responses / Show orphans

- **Include responses** — wenn aktiv, werden zu einer sichtbaren primären Anfrage auch ihre korrelierten Antwort-Events mit angezeigt, selbst wenn diese selbst nicht auf die Filterregeln passen (siehe Abschnitt 4).
- **Show orphans** — wenn aktiv, werden Antwort-Events angezeigt, deren zugehöriges Anfrage-Event nicht (mehr) im Puffer ist (z. B. weil es bereits verdrängt wurde).

**Empfehlung:** Beide Optionen im Regelfall aktiviert lassen — sonst sieht man z. B. bei einem Filter auf `llm_request` nur die Anfragen, aber nicht mehr die dazugehörigen Antworten, und verliert damit genau den Teil, der meist am interessantesten ist (Tokens, Ergebnis, Fehler). `Include responses` nur deaktivieren, wenn man bewusst ausschließlich die Anfrage-Seite sehen will, z. B. um zu zählen, wie oft ein bestimmter Tool-Aufruf pro Minute passiert, ohne durch die Antwort-Zeilen abgelenkt zu werden.

### 3.3 Gespeicherte Filter

Ein konfigurierter Filter kann unter einem Namen gespeichert werden:

| Element | Funktion |
|---------|---------|
| **Namensfeld + Save New** | Speichert die aktuelle Regel-Kombination samt `Include responses`/`Show orphans`-Einstellung unter diesem Namen. |
| **Update** | Überschreibt den aktuell geladenen gespeicherten Filter mit dem aktuellen Stand. |
| **Delete** | Löscht den aktuell geladenen gespeicherten Filter. |

Gespeicherte Filter werden zentral in `system.json5` (`system.ui.monitor.saved_filters`) abgelegt — sie sind also **für alle Nutzer des Systems sichtbar**, nicht nur lokal im eigenen Browser. Jeder gespeicherte Filter erscheint automatisch als Eintrag in der **linken Seitenleiste** des Monitor-Bereichs; ein Klick darauf lädt seine Regeln in den Filter Builder. Ohne gespeicherte Filter zeigt die Seitenleiste „No saved filters".

**Empfehlung:** Für jeden Agenten, den man regelmäßig beobachtet, einen eigenen gespeicherten Filter anlegen (z. B. „EURUSD AA" mit der Regel `Source contains OXS_T-EURUSD-AA`). Da diese Filter für alle Nutzer sichtbar sind, profitieren auch Kollegen sofort davon — man muss sich nicht gegenseitig erklären, wie man auf ein bestimmtes Pair filtert. Weil die Filter in `system.json5` liegen, sollte man vor dem Löschen eines fremden, unbekannten Filters kurz nachfragen — er könnte für jemand anderen aktiv im Gebrauch sein.

---

## 4. Gruppierte/korrelierte Events

Events, die eine `message_id` in ihrem Payload tragen, gelten als **primär** (eigenständige Anfrage). Events mit einer `correlation_id`, die auf die `message_id` eines anderen Events verweist, gelten als deren **Antwort** und werden standardmäßig darunter eingerückt angezeigt, sobald man auf das `[N]`-Badge der primären Zeile klickt.

- **`[N]`** neben einer primären Zeile — Anzahl korrelierter Antwort-Events; Klick klappt sie auf/zu.
- **`orphan`** (orange markiert) — ein Antwort-Event, dessen zugehöriges Anfrage-Event nicht im aktuellen Puffer gefunden wurde (z. B. bereits verdrängt, oder außerhalb des aktuellen Filters und `Include responses` ist deaktiviert).

Dieses Gruppieren ersetzt das frühere, separate „Bus Events"-Konzept: Anfrage/Antwort-Paare (z. B. ein `llm_request` und das zugehörige `llm_response`) erscheinen jetzt direkt zusammen an einer Stelle, statt über getrennte Tabs verteilt zu sein.

**Beispiel:** Ein Agent-Zyklus mit drei Tool-Aufrufen erzeugt ein primäres `agent_input_built`-Event mit `[3]` daneben. Klickt man darauf, erscheinen die drei zugehörigen `tool_call_completed`-Events eingerückt darunter, in der Reihenfolge, in der sie ausgeführt wurden — ohne dass man den Strom manuell nach zusammengehörigen Events absuchen muss.

**Achtung — viele `orphan`-Markierungen sind meist harmlos:** Direkt nach dem Öffnen des Monitors (frisch verbunden, Puffer noch leer) erscheinen die ersten paar Antwort-Events fast immer als `orphan`, weil ihre Anfrage bereits vorher passiert ist und nicht mehr im Puffer steht. Das ist normal und kein Fehler. Häufen sich Orphans aber dauerhaft mitten im laufenden Betrieb, deutet das eher auf sehr kurze Zeitabstände zwischen Anfrage und Verdrängung hin (Puffer läuft sehr schnell voll) — dann eher einen engeren Filter setzen, um weniger irrelevante Events durch den Puffer zu jagen.

---

## 5. Pinned Events

Über der Event-Liste erscheint ein eigener **„Pinned Events"**-Bereich, sobald mindestens ein Event angepinnt ist (auf-/zuklappbar).

- **Manuelles Anpinnen:** Pin-Icon einer Zeile anklicken. Angepinnte Events werden im Backend in einem geschützten Puffer gehalten, der **nicht** von der Ring-Buffer-Verdrängung betroffen ist — sie bleiben erhalten, auch wenn der 500er-Puffer im Browser längst weitergerückt ist. Ein `PinOff`-Klick entfernt die Markierung wieder.
- **Automatisches Anpinnen:** Bestimmte Fehler-/Abbruch-Ereignistypen werden vom System selbst automatisch angepinnt, sobald sie auftreten — erkennbar am `auto`-Badge in der Pinned-Liste:
  - `system_error`
  - `llm_error`
  - `llm_turn_failed`
  - `ec_run_failed`
  - `tool_call_failed`
  - `broker_error`
  - `broker_disconnected`

Der Pinned-Bereich wird alle 5 Sekunden vom Backend nachgeladen (`GET /monitoring/pinned`), unabhängig vom WebSocket-Strom — er zeigt also auch dann noch etwas, wenn die Live-Verbindung kurz unterbrochen war.

**Empfehlung:** Angepinnte Events sind ein gemeinsamer, geteilter Zustand des ganzen Systems (nicht nur des eigenen Browsers) — nützlich, um einem Kollegen gezielt auf ein bestimmtes Problem hinzuweisen, ohne Screenshots hin- und herzuschicken: einfach pinnen und sagen „schau dir den Pinned-Bereich an". Nach der Klärung nicht vergessen, wieder zu entpinnen (`PinOff`) — sonst sammeln sich im Pinned-Bereich über die Zeit viele nicht mehr relevante Altfälle an, die die eigentlich wichtigen (automatisch angepinnten Fehler) unnötig verdecken.

---

## 6. Event-Detail-Fenster

Ein Doppelklick auf eine Zeile (auch im Pinned-Bereich) öffnet ein schwebendes, **ziehbares und in der Größe veränderbares** Fenster mit den vollständigen Event-Daten.

### 6.1 Titelleiste

- Ereignis-Typ (farbcodiert), Zeitstempel, Broker/Pair (falls zutreffend)
- **Kopieren-Icon** — kopiert das vollständige JSON-Payload in die Zwischenablage
- **Schließen-Icon** (auch: **Escape**-Taste)

### 6.2 Kontext-Leiste

| Feld | Inhalt |
|------|--------|
| **What / Why** | Klartext-Erklärung, was dieser Ereignistyp bedeutet und warum er ausgelöst wurde — aus einem eingebauten Katalog der häufigsten Ereignistypen. Für unbekannte Typen erscheint ein Hinweis, dass keine Beschreibung hinterlegt ist. |
| **Source** | Das auslösende Modul (z. B. `agent:OXS_T-EURUSD-AA-ANLYS`, `broker.OXS_T`). |
| **Sender / Target** | Bus-Routing-Metadaten, falls im Payload vorhanden. |
| **Broker** | Broker-Modul und Pair, falls relevant. |
| **Msg / Corr** | `message_id` bzw. `correlation_id` des Events, falls vorhanden — nützlich, um dieselbe Kette manuell im [Event Log](ui.action.event_log.de.md) wiederzufinden. |

### 6.3 Payload

Vollständiges JSON, mit aufgelösten `\n`- und `\"`-Escape-Sequenzen für bessere Lesbarkeit. Nichts wird abgeschnitten.

### 6.4 Ziehen, Größe ändern, mehrere Fenster

Titelleiste klicken und ziehen zum Verschieben; jeder Rand/jede Ecke zum Vergrößern/Verkleinern. Das Fenster aktualisiert sich nicht automatisch — es bleibt auf das Event fixiert, das man geöffnet hat, auch wenn währenddessen neue Events eintreffen. Die zuletzt doppelt geklickte Zeile bleibt dunkelorange markiert, bis eine andere Zeile angeklickt wird.

**Achtung:** Es kann immer nur **ein** Detail-Fenster gleichzeitig offen sein — ein erneuter Doppelklick auf eine andere Zeile ersetzt das aktuell geöffnete Fenster, statt ein zweites daneben zu öffnen. Für einen direkten Payload-Vergleich zweier Events (z. B. `llm_request` vs. das zugehörige `llm_response`) bleibt daher meist nur: Payload per Kopieren-Icon sichern, dann das zweite Event öffnen.

---

## 7. Praktische Debug-Workflows

### 7.1 Vollständigen Analyse-Zyklus für ein Pair beobachten

1. Filter Builder: eine Regel `Source contains OXS_T-EURUSD-AA` hinzufügen (oder `Payload Field` mit passendem Pfad).
2. `Clear` klicken, um sauber zu starten.
3. Auf die nächste M5-Kerze warten.
4. Die Kette verfolgen: `agent_trigger_received` → `candles_request`/`candles_response` → `agent_input_built` → `llm_request` → `llm_turn_started`/`llm_turn_completed` → `llm_response` → `agent_decision_made` → bei BUY/SELL: `agent_signal_generated` → `ec_run_started`/`ec_run_completed`.
5. `llm_response` doppelklicken, um Token-Verbrauch und Entscheidung im Detail-Fenster zu sehen.
6. Bei wiederkehrendem Bedarf: den Filter unter einem Namen speichern (z. B. „EURUSD AA Zyklus").

### 7.2 Herausfinden, warum ein Agent nicht läuft

1. Filter: `Event Type equals agent_trigger_skipped`, optional zusätzlich `AND Source contains <agent_id>`.
2. Ein passendes Event doppelklicken und das `reason`-Feld im Payload prüfen:
   - `"session_filter"` → Agent liegt außerhalb seiner Handelssession.
   - `"any_candle_divider"` → AnyCandle-Teiler noch nicht erreicht.
   - `"runtime_paused"` → System ist pausiert.
   - `"already_running"` → vorheriger Zyklus noch nicht abgeschlossen.
   - `"disabled"` → Agent in der Konfiguration deaktiviert.
3. Erscheint gar kein `agent_trigger_skipped`: Filter auf `Event Type contains m5_candle` setzen und prüfen, ob überhaupt Kerzen für dieses Pair ankommen.

### 7.3 LLM-Aufrufe und Token-Verbrauch prüfen

1. Filter: `Event Type starts with llm_`.
2. Einen Execute-Lauf im Agent Chat starten oder auf einen natürlichen Zyklus warten.
3. `llm_response` doppelklicken; im Payload `input_tokens`/`output_tokens`, `latency_ms` und `decision` prüfen.
4. Erscheint stattdessen `llm_turn_failed`: `reason`-Feld auf den Fehlergrund prüfen — solche Fehler werden zusätzlich automatisch angepinnt (Abschnitt 5), gehen also nicht im Puffer verloren.

### 7.4 Broker-Verbindung überwachen

1. Filter: `Event Type contains broker_`.
2. Nach `broker_connected` beim Systemstart Ausschau halten.
3. `broker_http_request`/`broker_http_response`-Paare beobachten (per `[N]`-Badge aufklappbar) — `status_code` im Antwort-Payload prüfen (`200` ok, `4xx` Auth/Parameter-Fehler, `5xx` Server-Fehler).
4. `broker_disconnected` und `broker_error` werden automatisch angepinnt — auch nach einem vollen Ring-Buffer im Pinned-Bereich noch auffindbar.

### 7.5 Abgelehnten Trade untersuchen

1. Filter: `Event Type equals ec_run_output`, `Payload Field` mit Pfad `output_type` und Wert `order_rejected`.
2. Treffer doppelklicken; das `details`-Feld im Payload erklärt den Ablehnungsgrund.
3. Für die vollständige, dauerhafte Kette (auch aus der Vergangenheit) stattdessen das [Event Log](ui.action.event_log.de.md) mit derselben `correlation_id`/`message_id` durchsuchen — der Monitor zeigt nur, was seit dem letzten Neuladen der Seite live durchgelaufen ist.

---

## 8. Tipps für effektive Monitor-Nutzung

**Filter statt scrollen:** In einem aktiven System mit mehreren Agenten ist der ungefilterte Strom schnell unübersichtlich. Eine gezielte Regel-Kombination ist meist schneller als manuelles Scrollen.

**Wiederkehrende Filter speichern:** Eine Regel-Kombination, die man öfter braucht (z. B. „nur Fehler", „nur ein bestimmtes Pair"), unter einem Namen speichern — sie erscheint dann dauerhaft in der Seitenleiste, für alle Nutzer des Systems.

**Wichtige Einzelevents anpinnen statt nur zu kopieren:** Ein angepinntes Event bleibt erreichbar, auch wenn der Puffer längst weitergerückt ist — besser als das Payload in eine externe Notiz zu kopieren.

**Fehler-Events sind bereits gesichert:** Die automatisch angepinnten Fehlertypen (Abschnitt 5) muss man nicht zusätzlich manuell pinnen, um sie nicht zu verlieren.

**Monitor für „jetzt", Event Log für „damals":** Für alles, was gerade passiert oder gleich passieren wird, den Monitor nutzen. Für alles, was vor mehr als ein paar hundert Events oder vor einem Seiten-Neuladen passiert ist, das [Event Log](ui.action.event_log.de.md) verwenden.
