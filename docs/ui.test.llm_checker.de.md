[Zurück zu Test](ui.test.de.md)

# LLM Checker

`LLM Checker` sendet Nachrichtensequenzen direkt an ein konfiguriertes LLM-Modul und zeigt die vollständige Antwort inklusive Tool-Trace. Er ist bewusst vom Agent-Chat-Workflow getrennt — kein Agentenzyklus, keine Snapshot-Pipeline, keine Routing-Regeln. Was hier läuft, ist ein direktes LLM-Gespräch mit frei wählbarem Kontext.

Einsatzbereiche:
- LLM-Verbindung prüfen bevor ein Agent live geht
- System-Prompt-Varianten testen ohne den Agenten zu ändern
- Tool-Calling-Verhalten isoliert beobachten

---

## Layout

Die Seite ist zweigeteilt: links der Chat-Verlauf, rechts das Konfigurations-Panel.

---

## Konfigurations-Panel (rechts)

### LLM

Dropdown. **Pflichtfeld** — ohne Auswahl kann keine Nachricht gesendet werden. Zeigt alle LLM-Module aus der Systemkonfiguration.

Nach der Auswahl werden Temperature und Max Tokens automatisch mit den Modulwerten vorbelegt (können überschrieben werden).

### Agent

Dropdown. Optional. Bei Auswahl eines Agenten werden folgende Felder automatisch befüllt: Broker, Pair, System Prompt, erlaubte Tools. Sinnvoll um einen Agenten schnell in seinen Konfigurationskontext zu laden ohne ihn vollständig zu starten.

### Broker

Dropdown. Optional. Setzt den Broker-Kontext für Tools die einen Broker benötigen (z. B. `get_candles`, `place_order`).

### Pair

Textfeld. Optional. Währungspaar für den Kontext, z. B. `EURUSD`. Wird automatisch in Großbuchstaben umgewandelt.

### System Prompt

Textarea (4 Zeilen). Der Instruktionstext für das LLM. Standard: `"You are a helpful assistant. Use tools when necessary."`

Doppelklick öffnet ein verschiebbares Großformat-Editor-Fenster. Änderungen dort werden mit „Take over" übernommen oder mit „Close" verworfen.

### Temperature

Textfeld. Steuert die Zufälligkeit der LLM-Ausgabe (0.1 = deterministisch, 1.0 = kreativ). Wird aus dem LLM-Modul vorbelegt. Kann leer gelassen werden. Muss eine Zahl sein wenn ausgefüllt.

### Max Tokens

Textfeld. Maximales Token-Budget für die Antwort. Wird aus dem LLM-Modul vorbelegt. Muss eine Zahl sein wenn ausgefüllt.

### Max Tool Turns

Textfeld. Maximale Anzahl an Tool-Aufruf-Iterationen pro Nachricht. Standard: `8`. Verhindert Endlosschleifen. Muss eine Zahl sein.

### Tool Filter

Textfeld. Filtert die Tool-Liste nach Name oder Beschreibung (Groß-/Kleinschreibung egal). Hilfreich wenn viele Tools konfiguriert sind.

### Select visible / Clear visible

Zwei Schaltflächen:
- **Select visible**: Aktiviert alle aktuell gefilterten Tools auf einmal
- **Clear visible**: Deaktiviert alle aktuell gefilterten Tools auf einmal

### Tool-Checkboxen

Eine Checkbox pro verfügbarem Tool. Nur aktivierte Tools werden dem LLM für diesen Test zur Verfügung gestellt. Standardmäßig leer — Tools müssen bewusst aktiviert werden.

---

## Chat-Panel (links)

### Nachrichteneingabe

Textarea (3 Zeilen). Die Nachricht an das LLM. Enter sendet, Shift+Enter fügt Zeilenumbruch ein.

Deaktiviert wenn: kein LLM ausgewählt, Anfrage läuft gerade.

### Send

Sendet die Nachricht mit der aktuellen Konfiguration. Deaktiviert wenn: kein LLM, leere Nachricht, oder Anfrage läuft.

### Clear chat

Löscht den gesamten Chatverlauf, Tool-Trace und alle Metadaten.

---

## Chat-Verlauf

Wechselnde Nachrichten-Bubbles:
- **Grün**: User-Nachrichten
- **Blau**: Assistent-Antworten mit Zeitstempel

Während einer laufenden Anfrage wird „Running LLM + tool loop..." angezeigt.

---

## LLM ↔ Tool Trace

Aufklappbarer Bereich unterhalb des Verlaufs. Zeigt den internen Ablauf der letzten Anfrage:

**LLM-Einträge (pro Turn):**
- Turn-Nummer
- Stop-Reason (z. B. `tool_use`, `end_turn`)
- Anzahl Tool-Aufrufe
- Antworttext (gekürzt auf 380 Zeichen)

**Tool-Einträge (pro Aufruf):**
- Tool-Name
- Turn-Nummer
- Argumente
- Ergebnis (gekürzt auf 320 Zeichen)

**Metadaten:**
- Gesamte Token-Anzahl
- Finaler Stop-Reason

---

## Fehlermeldungen

Werden direkt im Chat angezeigt wenn:
- Temperature, Max Tokens oder Max Tool Turns keine gültige Zahl sind
- Die API einen Fehler zurückgibt

---

## Typischer Ablauf

1. **LLM** auswählen
2. Optional: **Agent** auswählen (füllt Kontext vor)
3. System Prompt anpassen wenn nötig
4. Relevante **Tools** aktivieren
5. Nachricht eingeben und senden
6. Antwort und Tool-Trace prüfen

---

## Zweck und Philosophie

Der LLM Checker ist der schnellste Weg, jede im System registrierte LLM-Konfiguration zu testen, ohne aktive Agenten zu beeinflussen. Im Gegensatz zu Agent Chat — der Nachrichten durch die gesamte Agenten-Pipeline leitet, inklusive Snapshot-Builder, Event-Bus, Tool-Orchestrierung und Session-Filter — sendet der LLM Checker Anfragen direkt an das LLM-Modul und liefert rohe Antworten. Diese Isolation ist sein Kernwert.

**Was den LLM Checker von Agent Chat unterscheidet:**

Wenn ein AA-Agent normal läuft, ist die Pipeline:
1. Ein Ereignis triggert den Agenten
2. Der Snapshot-Builder sammelt Kerzen, Indikatoren, Swing-Level und Kontodaten
3. All dieser Kontext wird in den System-Prompt-Bereich eingefügt
4. Der vervollständigte Prompt wird an das LLM gesendet
5. Das LLM antwortet, ruft ggf. Tools auf
6. Das Ergebnis wird als Ereignis auf dem Bus veröffentlicht

Der LLM Checker überspringt Schritte 1, 2, 3 und 5 komplett. Du erhältst ein direktes Gespräch mit dem LLM — genau das was du eingegeben hast, genau der System Prompt den du geschrieben hast, genau die Tools die du aktiviert hast. Nichts weiter.

Das bedeutet:
- Ein Test im LLM Checker reproduziert nicht automatisch das vollständige Agenten-Verhalten
- Für eine genaue Reproduktion des Agenten-Verhaltens muss das tatsächliche Snapshot-JSON als User-Message eingefügt werden
- Für das Testen des rohen LLM-Denkens, der Prompt-Befolgung und der Tool-Call-Logik ist der LLM Checker ideal

---

## Konfigurations-Panel — Detaillierte Referenz

### LLM-Modul-Selektor

Dropdown mit allen LLM-Modulen, die in `config/system.json5` unter `modules.llm` definiert sind. **Pflichtfeld** — ohne Auswahl kann keine Nachricht gesendet werden.

Nach Auswahl eines LLM-Moduls werden Temperature und Max Tokens automatisch mit den konfigurierten Standard-Werten des Moduls vorbelegt. Diese Werte können für diese Test-Session überschrieben werden, ohne die Basis-Konfiguration des Moduls zu ändern.

Beispiele für LLM-Module:
- `azure_azmin` — Azure OpenAI Deployment
- `anthropic_claude` — Anthropic Claude über API
- `openai_gpt4` — OpenAI GPT-4 direkt

Das LLM-Modul bestimmt den Modell-Provider, API-Key, Endpoint und Standard-Parameter. Alles davon ist in der Modul-Konfigurationsdatei unter `modules/llm/` definiert.

### Agent-Selektor

Dropdown mit allen Agenten im System. **Optional**, aber äußerst nützlich. Bei Auswahl eines Agenten werden automatisch vorbelegt:
- **Broker** — aus dem Broker-Feld des Agenten
- **Pair** — aus dem Pair-Feld des Agenten
- **System Prompt** — aus dem system_prompt-Feld des Agenten
- **Allowed Tools** — Checkboxen entsprechend der `allowed_tools`-Liste des Agenten
- **Temperature** — aus der tool_config des Agenten oder dem LLM-Modul-Standard
- **Max Tokens** — aus der tool_config des Agenten

Dies macht den Workflow "Agent wählen, direkt testen" zu einem Klick: den zu debuggenden Agenten auswählen, und der LLM Checker ist so konfiguriert, dass er den Kontext des Agenten imitiert.

**Wichtig:** Ein Agent auszuwählen ändert nichts am Agenten. Alle vorausgefüllten Werte sind lokal für diese Session. Der Live-Agent läuft weiterhin mit seiner eigenen unveränderten Konfiguration.

### Broker-Selektor

Dropdown mit allen Broker-Modulen. **Optional.** Wenn gesetzt, wird dieser Wert an alle Tools übergeben, die einen Broker-Parameter akzeptieren (z.B. `get_order_book`, `place_order`, `get_account_status`).

Kann unabhängig vom Agent-Selektor überschrieben werden — zum Beispiel um EURUSD-Agenten-Logik gegen einen Paper-Trading-Broker zu testen.

### Pair-Eingabe

Textfeld für ein Währungspaar wie `EURUSD`, `GBPUSD`, `USDJPY`. Wird automatisch in Großbuchstaben umgewandelt. **Optional.** Tools, die ein Pair benötigen (wie `get_candles`), erhalten diesen Wert.

Das Feld ist eine Datalist-Eingabe und zeigt beim Tippen Vorschläge aus bekannten Agenten-Konfigurationen. Es kann auch jedes beliebige gültige Pair eingetippt werden.

### System Prompt

Textarea (standardmäßig 4 Zeilen). Der Instruktionstext, den das LLM zu Beginn jedes Gesprächs in dieser Session erhält.

Standard-Wert wenn nichts geladen ist: `"You are a helpful assistant. Use tools when necessary."`

**Editor erweitern:** Doppelklick auf die Textarea öffnet ein großformatiges, verschiebbares Modal-Fenster. Dieses Modal bietet eine volle Höhe für Prompts von mehreren hundert Zeilen. "Take over" im Modal übernimmt die Änderungen, "Close" verwirft sie.

**Take-over-Schaltfläche:** Erscheint neben dem System-Prompt-Feld. Wenn ein Agent ausgewählt ist, kopiert "Take over" den aktuellen System Prompt des Agenten wortwörtlich in den Editor. Dies ist der primäre Mechanismus für das Debugging: den exakten Prompt laden den der Agent verwendet, dann direkt ändern oder testen.

Wenn der gewählte Agent keinen System Prompt hat, leert "Take over" den Editor.

**Prompt-Gültigkeitsbereich:** Der System Prompt gilt für die gesamte Session. Jede Nachricht wird von diesem System Prompt begleitet. Wenn der Prompt mid-Session geändert wird, gilt die neue Version für alle nachfolgenden Nachrichten, aber der Konversationsverlauf von davor bleibt erhalten.

Best Practice: Chat leeren wenn der System Prompt wesentlich geändert wird.

### Temperature

Steuert die Zufälligkeit der LLM-Ausgabe (0.0 bis 2.0 je nach Modell):
- `0.0–0.1`: hochgradig deterministisch, empfohlen für Analyse- und Trading-Entscheidungen
- `0.3–0.5`: ausgeglichen, leichte Variation zwischen Runs
- `0.7–1.0`: merkliche Kreativität und Variation
- Über `1.0`: erhebliche Unvorhersehbarkeit, selten nützlich für Trading

Wird aus dem LLM-Modul-Standard vorbelegt. Kann leer gelassen werden. Muss eine gültige Zahl sein wenn ausgefüllt.

Für das Testen von System Prompts Temperature auf `0.1` halten für konsistente, reproduzierbare Antworten.

### Max Tokens

Maximales Ausgabe-Token-Budget pro Antwort. Erhöhen wenn Antworten abgeschnitten werden. Verringern für schnelles iteratives Testen.

Typische Werte:
- `1000–2000`: kurze, entscheidungsorientierende Antworten (für BA-Agent-Tests)
- `4000–8000`: detaillierte Analyse (für AA-Agent-Tests)
- `16000+`: sehr lange Analysen

### Max Tool Turns

Maximale Anzahl an Tool-Call-Iterationen pro Nachricht. Standard: `8`.

Jeder "Turn" ist ein Zyklus: LLM ruft Tool auf → Tool liefert Ergebnis → LLM fährt fort. Auf `1` setzen erzwingt Stopp nach dem ersten Tool-Call. Auf `15` oder höher setzen erlaubt komplexe mehrstufige Denkketten.

### Tool Filter

Textfeld zur Filterung der angezeigten Tool-Checkboxen nach Name oder Beschreibung (Groß-/Kleinschreibung egal). "candle" eingeben zeigt nur Tools mit "candle" im Namen, "order" zeigt order-bezogene Tools.

### Select Visible / Clear Visible

- **Select visible**: aktiviert alle aktuell sichtbaren Checkboxen
- **Clear visible**: deaktiviert alle aktuell sichtbaren Checkboxen

Nützlich für schnelle Massenauswahl: nach "get_" filtern, dann "Select visible" klicken aktiviert alle Nur-Lese-Marktdaten-Tools auf einmal.

### Tool-Checkboxen

Eine Checkbox pro registriertem Tool. Nur aktivierte Tools werden dem LLM als verfügbar übergeben.

**Standardmäßig leer.** Tools müssen bewusst aktiviert werden. Ohne Tools antwortet das LLM ausschließlich auf Basis seines Trainings und des System Prompts.

**Warnung bei Order-Execution-Tools:** `place_order`, `auto_place_order`, `close_position` oder `modify_order` zu aktivieren erlaubt dem LLM echte Orders während dieser Test-Session aufzugeben. Der LLM Checker nutzt den im Broker-Dropdown gewählten Broker. Nur auf Demo-/Test-Broker-Konten verwenden, es sei denn die Live-Order-Ausführung wird gezielt getestet.

---

## Chat-Panel — Detaillierte Referenz

### Nachrichteneingabe

Textarea (3 Zeilen). Nachricht an das LLM eingeben.

- **Enter**: sendet sofort
- **Shift+Enter**: fügt Zeilenumbruch ein ohne zu senden
- Deaktiviert während eine Anfrage läuft

Es kann jeder Text eingefügt werden — JSON-Payloads, strukturierte Marktanalysen, oder Beispiel-Tool-Ausgaben — um zu simulieren was ein Agent empfangen würde.

### Senden-Schaltfläche

Sendet die aktuelle Nachricht. Zeigt einen Spinner während der Verarbeitung. Deaktiviert wenn: kein LLM-Modul gewählt, Eingabe leer, oder Anfrage läuft.

### Chat leeren

Entfernt alle Nachrichten aus dem Konversationsverlauf. Bestätigungsdialog verhindert versehentliches Löschen. Löscht NICHT die System-Prompt-, Tool-Auswahl- oder Kontext-Felder.

Chat leeren:
- Bei wesentlichen Änderungen am System Prompt
- Zwischen verschiedenen Test-Szenarien
- Vor A/B-Vergleichen

---

## Chat-Verlauf — Nachrichtentypen

### User-Nachrichten

Rechts angezeigt mit grünem/blauem Hintergrund (je nach UI-Theme). Jede Nachricht zeigt:
- Den Nachrichtentext
- Zeitstempel (HH:MM:SS)
- Kopieren-Schaltfläche

### Assistent-Nachrichten

Links angezeigt mit Markdown-Rendering (Überschriften, Fett, Code-Blöcke, Tabellen, Listen). Jede Nachricht zeigt:
- Gerenderte Antwort
- Zeitstempel
- Kopieren-Schaltfläche (kopiert rohes Markdown)
- Token-Nutzung im Trace unten

### System-Nachrichten

Zentrierte neutrale Streifen für informative Ereignisse: Session geleert, Konfiguration geändert, API-Fehler, Max-Tool-Turns erreicht.

### Laufanzeige

Während der Verarbeitung erscheint "Running LLM + tool loop..." im Chat-Bereich mit pulsierendem Indikator.

---

## LLM ↔ Tool Trace — Detaillierte Referenz

Unterhalb des Chat-Verlaufs befindet sich ein aufklappbarer Bereich "LLM ↔ Tool Trace". Er zeigt das interne Turn-für-Turn Ausführungsprotokoll der letzten Anfrage.

### Aufbau

Der Trace ist als sequenzielle Liste von Turns organisiert. Jede Anfrage startet bei Turn 1 und erhöht sich für jede Tool-Calling-Runde.

**LLM-Eintrag (pro Turn):**

| Feld | Beschreibung |
|---|---|
| Turn | Turn-Nummer (1, 2, 3...) |
| Stop-Reason | Warum das LLM gestoppt hat: `tool_use` (Tool aufgerufen), `end_turn` (Antwort beendet) |
| Tool Calls | Anzahl der Tool-Aufrufe in diesem Turn |
| Antworttext | Erste 380 Zeichen der Textantwort |

**Tool-Eintrag (pro Aufruf):**

| Feld | Beschreibung |
|---|---|
| Tool-Name | Name des aufgerufenen Tools |
| Turn | Zu welchem Turn dieser Aufruf gehört |
| Argumente | Die vom LLM übergebenen Argumente |
| Ergebnis | Erste 320 Zeichen des Tool-Ergebnisses |

**Metadaten (Ende des Trace):**

| Feld | Beschreibung |
|---|---|
| Gesamt-Tokens | Input + Output Tokens dieser Anfrage |
| Stop-Reason | Finaler Stop-Grund der gesamten Anfrage |

### Was im Trace zu suchen ist

**Falsche Tool-Argumente:** Der Trace zeigt genau welche Argumente das LLM gewählt hat. Wenn `get_candles` mit `timeframe="M1"` aufgerufen wurde aber `H1` erwartet wurde, ist das sofort sichtbar.

**Fehlende Tool-Aufrufe:** Wenn das LLM ohne Tool-Aufrufe geantwortet hat obwohl es welche hätte machen sollen, zeigt der Trace Stop-Reason `end_turn` mit null Tool Calls in Turn 1.

**Zu viele Tool-Turns:** Wenn der Trace 8+ Turns zeigt, befindet sich das LLM möglicherweise in einer Schleife.

**Token-Verbrauch:** Hohe Token-Zahlen pro Anfrage erscheinen in den Metadaten.

---

## Fehlerbehandlung

Fehler erscheinen als System-Nachrichten im Chat-Bereich (roter Hintergrund).

**Validierungsfehler** (vor dem Senden):
- "Temperature must be a number" — kein gültiger Zahlenwert
- "Max Tokens must be a number" — kein gültiger Zahlenwert
- "Max Tool Turns must be a number" — kein gültiger Zahlenwert

**API-Fehler** (nach dem Senden):
- "Rate limit exceeded" — Anbieter hat die Anfrage gedrosselt; warten und wiederholen
- "Context length exceeded" — System Prompt + Konversationsverlauf + Tool-Schemas überschreiten das Kontext-Fenster des Modells
- "API key invalid" — LLM-Modul hat einen falschen API-Key
- HTTP-5xx-Fehler — Anbieter-seitige Probleme

**Tool-Fehler:**
- Bei fehlgeschlagenem Tool-Call erscheint der Fehler inline im Tool-Trace in Rot
- Das LLM erhält den Fehlertext als Tool-Ergebnis

---

## Praktische Test-Workflows

### Workflow 1: Neuen System Prompt vor dem Deployment testen

**Ziel:** Einen überarbeiteten AA-Agenten-System-Prompt validieren bevor er in der Live-Agenten-Konfiguration gespeichert wird.

**Schritte:**

1. LLM Checker im Test-Panel öffnen
2. EURUSD AA-Agent aus dem Agent-Dropdown wählen
   - Füllt vor: LLM-Modul, Broker, Pair=EURUSD, System Prompt, Tool-Checkboxen
3. "Take over" klicken um zu bestätigen dass der aktuelle Live-Prompt geladen ist
4. System-Prompt-Editor erweitern (Textarea doppelklicken) um das Modal zu öffnen
5. Prompt bearbeiten — Abschnitte hinzufügen, ändern oder umstrukturieren
6. "Take over" im Modal klicken um anzuwenden
7. Relevante Tools aktivieren: `get_candles`, `calculate_indicator`, `get_swing_levels`
8. Repräsentative Test-Nachricht eingeben: `"Analysiere die aktuellen EURUSD-Marktbedingungen auf H1 und H4. Gib eine Handelsentscheidung mit Entry, SL und TP."`
9. Senden und beobachten:
   - Ruft das LLM die erwarteten Tools auf?
   - Folgt die Antwort den Formatierungsregeln im Prompt?
   - Wird die Entscheidungslogik korrekt angewendet?
10. Iterieren: Prompt anpassen, Chat leeren, gleiche Nachricht erneut senden
11. Nach Zufriedenheit: finalen Prompt-Text kopieren und in Agent Config einfügen

**Zeitschätzung:** 5–30 Minuten je nach Prompt-Komplexität.

### Workflow 2: Unerwartete Agenten-Entscheidung reproduzieren

**Ziel:** Ein Agent hat bei einem starken Abwärtstrend eine BUY-Order aufgegeben. Ursache verstehen.

**Voraussetzung:** Du hast die Analyseausgabe aus dem Agenten-Log. Es ist ein JSON-Objekt mit Feldern wie `decision`, `confidence`, `analysis_summary`, `order_start_signal`.

**Schritte:**

1. Den relevanten BA-Agenten aus dem Agent-Dropdown wählen
2. "Take over" klicken um den BA-Agenten-System-Prompt zu laden
3. Alle Order-Execution-Tools deaktivieren (`place_order`, `auto_place_order`) — ohne echte Orders testen
4. Das exakte Analyse-JSON das der AA-Agent produziert hat als User-Message einfügen
5. Senden und beobachten was das LLM des BA-Agenten entscheidet
6. Wenn die gleiche unerwartete Entscheidung getroffen wird: Problem liegt im BA-Prompt
7. Wenn eine vernünftige Entscheidung getroffen wird: Problem liegt möglicherweise in der Event-Zustellung oder Snapshot-Injektion

### Workflow 3: Tool-Output-Qualität validieren

**Ziel:** Überprüfen ob `get_swing_levels` korrekte H4-Swing-Level für GBPUSD liefert.

**Schritte:**

1. Beliebigen GBPUSD-Agenten auswählen oder Pair = GBPUSD manuell setzen
2. Nur `get_swing_levels` aktivieren
3. Minimalen System Prompt schreiben: `"Du bist ein Daten-Inspektor. Bei Swing-Level-Anfragen rufe get_swing_levels auf und zeige alle zurückgegebenen Daten wortgetreu an."`
4. Senden: `"GBPUSD H4 Swing-Level abrufen, max 8 Level, nach Prominenz sortiert."`
5. LLM ruft `get_swing_levels` auf — Tool-Ergebnis im Trace aufklappen
6. Zurückgegebene Level mit Chart vergleichen
7. Bei falschen Leveln: Tool Executor für direkte Parameterkontrolle nutzen

### Workflow 4: Multi-Turn Kontext-Konsistenz-Test

**Ziel:** Überprüfen ob das LLM konsistentes Denken über mehrere Nachrichten aufrecht erhält.

**Schritte:**

1. AA-Agenten-Prompt laden
2. `get_candles` und `calculate_indicator` aktivieren
3. Senden: `"Wie ist der Gesamttrend auf H4 EURUSD basierend auf den letzten 50 Kerzen?"`
4. Nach der Antwort: `"Jetzt H1 prüfen. Stimmt es mit dem H4-Trend überein oder widerspricht es ihm?"`
5. Nach der Antwort: `"Welche Richtung würdest du jetzt wählen und warum?"`
6. Auswerten: Ist die finale Richtung konsistent mit den früheren Einschätzungen?

### Workflow 5: Zwei Prompt-Versionen vergleichen

**Ziel:** Bestimmen welche von zwei Prompt-Versionen einen bestimmten Edge-Case besser behandelt.

**Schritte:**

1. Prompt Version A in den System-Prompt-Editor einfügen
2. 4–5 standardisierte Test-Nachrichten senden
3. Antworten notieren (oder kopieren)
4. "Chat leeren" klicken
5. Prompt Version B in den Editor einfügen
6. Dieselben 4–5 Nachrichten senden
7. Antworten vergleichen

---

## Wichtige Konzepte und Fallstricke

### Kein Snapshot-Building

**Der LLM Checker erstellt keinen Snapshot.** Wenn ein AA-Agent in Produktion läuft, erhält er einen reichhaltigen Kontext-Block, der Kerzen, Indikatoren, Swing-Level, Kontostatus und mehr enthält — alles vom Snapshot-Builder vorausgefüllt.

Im LLM Checker weiß das LLM nur was du ihm mitteilst. Für eine genaue Simulation: das tatsächliche Snapshot-Output aus den Agenten-Logs kopieren und als User-Message einfügen.

### Session-Zustand

Der Konversationsverlauf wird für die gesamte Session beibehalten bis "Chat leeren" geklickt oder die Seite neu geladen wird. Bei wesentlichen System-Prompt-Änderungen immer zuerst den Chat leeren.

### Tool-Aufrufe sind real

Im LLM Checker ausgeführte Tools laufen gegen das Live-System mit echten Daten. `get_candles` liefert echte Marktdaten. `get_account_status` liefert echte Kontoinformationen. `place_order` gibt echte Orders auf. Es gibt keinen Sandbox-Modus.

### Token-Zählung

Die Token-Zahl in den Metadaten umfasst System Prompt, alle vorherigen Nachrichten, Tool-Schemas und die aktuelle Antwort. Bei hohen Token-Zahlen oder Kontextlängen-Fehlern: Chat leeren, unbenötigte Tools deaktivieren oder System Prompt verkürzen.

---

## Zusammenfassung: Wann LLM Checker vs. andere Tools nutzen

| Aufgabe | Empfohlenes Tool |
|---|---|
| Neuen System Prompt entwerfen und testen | LLM Checker |
| Agenten-Entscheidung reproduzieren | LLM Checker (Snapshot als Nachricht einfügen) |
| Rohen Tool-Output prüfen (exakte Parameter) | Tool Executor |
| Vollständigen Agenten-Zyklus mit Snapshot beobachten | Agent Chat |
| Mehrere Prompts schnell testen | LLM Checker (zwischen Runs leeren) |
| Tool-Call-Argumente debuggen die vom LLM gewählt werden | LLM Checker (Trace lesen) |
| Getesteten Prompt in Live-Agenten deployen | Agent Config |
| Live-Agenten-Verhalten überwachen | Monitor-Panel |
