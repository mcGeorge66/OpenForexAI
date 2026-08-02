[Zurück zu Action](ui.action.de.md)

# Prompt Workbench (PWB) — Handbuch

Die **Prompt Workbench** (Abkürzung: **PWB**) ist der Ort, an dem man einen Agent-System-Prompt **entwickelt, verfeinert und gegen echte Vergangenheitsdaten testet**, ohne dabei das laufende Live-System oder einen echten Broker anzufassen. Chat, Step und Run laufen über einen provisorischen Agenten, der exakt dieselbe LLM-/Tool-Use-Schleife verwendet wie die echten Trading-Agenten (`Agent._run_with_tools`) — was hier funktioniert, funktioniert prinzipiell genauso in Produktion.

## Wofür ist das gut?

Typische Situationen, in denen man die PWB statt eines Live-Agenten benutzt:

- **Einen neuen Prompt entwickeln**, bevor er einem echten Agenten zugewiesen wird — z. B. „ich möchte einen Agenten, der wie ein bestimmter bekannter Trading-Stil handelt" (siehe Beispiel unten).
- **Nachvollziehen, warum ein Live-Agent zu einer bestimmten Einschätzung kommt** — denselben Prompt, dieselben Kerzen laden und live mitverfolgen, statt aus Logs zu raten.
- **Eine Handelsidee über eine ganze Zeitreihe durchspielen** (Simulation/Run), bevor man sie scharf schaltet.
- **Prompt-Varianten vergleichen** — z. B. zwei unterschiedliche Formulierungen gegen exakt dieselben Kerzen laufen lassen und die Antworten gegenüberstellen.
- **Reasoning-Effort-Stufen vergleichen** — dieselbe Frage bei `low` vs. `high` stellen, um zu sehen, ob mehr Reasoning tatsächlich bessere Analysen liefert oder nur Zeit/Kosten kostet.

**Was die PWB nicht ist:** kein Ersatz für den Snapshot Designer (der bleibt die Quelle für die Produktions-Datenpipeline) und kein Ort, an dem Prompt-Änderungen automatisch live werden — siehe die Warnung in Abschnitt 7.

---

## Inhaltsverzeichnis

1. [Seitenaufbau](#1-seitenaufbau)
2. [Workbench Config — New / Load / Save / Delete](#2-workbench-config--new--load--save--delete)
3. [Kerzenlade-Leiste](#3-kerzenlade-leiste)
4. [Simulations-Steuerung in der Kopfleiste](#4-simulations-steuerung-in-der-kopfleiste)
5. [Chart-Bereich](#5-chart-bereich)
6. [Linke Spalte: Chat](#6-linke-spalte-chat)
7. [Linke Spalte: Prompt](#7-linke-spalte-prompt)
8. [Rechte Spalte: Analyse-Tab](#8-rechte-spalte-analyse-tab)
9. [Rechte Spalte: Simulation-Tab](#9-rechte-spalte-simulation-tab)
10. [Rechte Spalte: LLM-Context-Tab](#10-rechte-spalte-llm-context-tab)
11. [Annotation-Tools des Agenten](#11-annotation-tools-des-agenten)
12. [Frozen-Window-Prinzip: warum das wichtig ist](#12-frozen-window-prinzip-warum-das-wichtig-ist)
13. [Häufige Probleme](#13-häufige-probleme)
14. [Ausführliches Beispiel: einen Prompt von Grund auf entwickeln](#14-ausführliches-beispiel-einen-prompt-von-grund-auf-entwickeln)
15. [Weitere Arbeitsabläufe](#15-weitere-arbeitsabläufe)

---

## 1. Seitenaufbau

Die Seite gliedert sich von oben nach unten:

1. **Workbench-Config-Leiste** — Sitzung als benanntes Preset speichern/laden.
2. **Kerzenlade-Leiste** — Broker, Pair, Timeframe, Kerzenanzahl, Anchor-Datum, Simulation-Steuerung.
3. **Chart** — per Ziehgriff in der Höhe verstellbar (160–800 px).
4. **Unterer Bereich, zwei Spalten:**
   - **Links:** Tabs `Chat` / `Prompt`
   - **Rechts:** Tabs `Analyse` / `Simulation` / `LLM Context`

---

## 2. Workbench Config — New / Load / Save / Delete

Ganz oben. Speichert bzw. lädt ein vollständiges Workbench-Preset unter einem frei wählbaren Namen (Autovervollständigung zeigt vorhandene Namen).

| Element | Funktion |
|---------|---------|
| **New** | Setzt die gesamte Workbench auf einen leeren Zustand zurück — Kerzen, Chat, Annotationen, Simulation, Prompt, Tool-Blocks, alles. |
| **Namensfeld** | Name des Presets, mit Vorschlagsliste bereits gespeicherter Presets. |
| **Load** | Lädt das Preset mit diesem Namen. |
| **Save** | Speichert den aktuellen Zustand unter diesem Namen (überschreibt ein gleichnamiges Preset). |
| **Delete** | Löscht das Preset mit diesem Namen. |

**Im Preset gespeichert:** Broker, Pair, Timeframe, Kerzenanzahl, Anchor-Datum, Annotationsfarbe, Step-Size, Auto-Trade-Status, aktiver Chat/Prompt-Tab, aktiver Analyse/Simulation-Tab, System-Prompt, LLM-Auswahl, Reasoning Effort, Indikatoren (Analyse-Tab), tool_blocks/calculation_blocks/assembly_transform_script (Simulation-Tab).

**Nicht im Preset enthalten** (Sitzungszustand, keine Konfiguration): geladene Kerzen, Chatverlauf, gezeichnete Annotationen, aktuelle Simulationsposition.

**Empfehlung:** Sobald ein Prompt-Entwurf zum ersten Mal brauchbare Antworten liefert, sofort unter einem eigenen Namen speichern (z. B. `andrew_krieger_v1`), bevor weiter experimentiert wird. Ein Klick auf `New` oder ein Neuladen der Seite räumt sonst alles ohne Rückfrage weg — es gibt keinen Undo. Für mehrere Prompt-Varianten lohnt sich ein Namensschema wie `strategie_v1`, `strategie_v2`, damit man später per Load direkt vergleichen kann.

> Der `LLM Context`-Tab ist eine reine Live-Vorschau und kein eigener Modus — beim Speichern wird er automatisch auf `Analyse` abgebildet, damit das Preset-Schema stabil bleibt.

---

## 3. Kerzenlade-Leiste

| Element | Funktion |
|---------|---------|
| **Broker-Dropdown** | Nur sichtbar bei mehr als einem verbundenen Broker. Bei genau einem wird der Name nur angezeigt. |
| **Pair-Dropdown** | Währungspaar, aus den aktiven Agent-Konfigurationen ermittelt. |
| **Timeframe-Buttons** | M5 bis D1 (kein M1). |
| **Candles** | Anzahl zu ladender Kerzen, 20–2000. Reagiert erst beim Verlassen des Felds (Blur) oder mit Enter, nicht bei jedem Tastenanschlag. |
| **Anchor date** | Optional. Wenn gesetzt, werden Kerzen bis `<Datum> 23:59:59` geladen statt der aktuellsten. |
| **Load** | Lädt die Kerzen neu. Wird auch automatisch bei jeder Änderung von Pair/Timeframe/Kerzenanzahl/Anchor-Datum ausgelöst. |

**Empfehlung zur Kerzenanzahl:** Für einen schnellen Prompt-Test (wenige Fragen, schnelles Iterieren) reichen oft 100–200 Kerzen — jede Chat-Nachricht wird dadurch kürzer und schneller/günstiger beantwortet. Für eine realistische Simulation über mehrere Handelstage sollte die Anzahl so gewählt werden, dass der gewünschte Zeitraum plus etwas Vorlauf hineinpasst (z. B. 500 M5-Kerzen ≈ gut 1,7 Handelstage) — sonst läuft die Simulation schneller aus als geplant.

**Achtung — Anchor-Datum vergessen:** Wenn man für einen Test bewusst ein Anchor-Datum gesetzt hat, um eine bestimmte Vergangenheitssituation zu laden, bleibt es beim nächsten `Load` aktiv, wenn man es nicht manuell über `×` zurücksetzt. Ein häufiger Verwirrungs-Moment: man wechselt das Pair, klickt `Load`, bekommt aber weiterhin alte Daten von vor Wochen — weil das Anchor-Datum noch stand. Bei „warum sind das nicht die aktuellen Kerzen" zuerst hier nachsehen.

Beim Laden wird intern der Zeitstempel der neuesten geladenen Kerze als **Anchor** gemerkt (`candle_anchor`) und mit jeder folgenden Chat-/Simulation-/Preview-Anfrage mitgeschickt — siehe [Abschnitt 12](#12-frozen-window-prinzip-warum-das-wichtig-ist).

---

## 4. Simulations-Steuerung in der Kopfleiste

Rechts neben `Load`, durch einen Trenner abgesetzt:

| Element | Funktion |
|---------|---------|
| **Position** | Zahlenfeld 0…total. Zählt **rückwärts**: `total` = älteste Kante des geladenen Fensters (nichts sichtbar), `0` = vollständig aufgedeckt (alle Kerzen sichtbar). |
| **Step size** | Anzahl Kerzen, um die `Step`/`Run` die Position je Schritt verringert. |
| **Step** | Führt genau einen Simulationsschritt aus: Position sinkt um `Step size`, der Agent bekommt eine Nachricht mit dem neu sichtbaren Fenster und wird gebeten, zu entscheiden (halten/öffnen/schließen) und dies ggf. per `trade_marker` festzuhalten. |
| **Run / Stop** | Führt `Step` wiederholt aus (500 ms Pause dazwischen) bis Position `0` erreicht ist oder `Stop` gedrückt wird. |
| **sichtbar: X / Y (Kerzen Y–Position)** | Erscheint nur bei Position > 0 — zeigt das aktuell für den Agenten sichtbare Fenster an. |
| **Clear chart** | Entfernt alle vom Agenten gezeichneten Annotationen vom Chart. Betrifft **nicht** den Chatverlauf (dafür: `Delete` im Chat-Tab, Abschnitt 6). |
| **Reset** | Setzt Zoom/Pan des Charts zurück. |

**Empfehlung:** Vor dem ersten `Run` immer erst ein- oder zweimal `Step` klicken und die Antworten lesen. `Run` ruft das LLM automatisch und wiederholt auf — bei einer Fehlkonfiguration (z. B. zu wenig sichtbarer Kontext, ein Prompt, der den Agenten in eine Endlos-Rechtfertigungsschleife treibt) merkt man das mit `Step` sofort und günstig, mit `Run` erst nach vielen unnötigen LLM-Aufrufen.

**Achtung — Kosten/Zeit bei `Run`:** Jeder Simulationsschritt ist ein echter LLM-Aufruf. Bei `Step size = 3` und 500 geladenen Kerzen sind das rund 165 Aufrufe bis Position 0 — bei einem teuren Modell oder hohem Reasoning Effort kann ein vollständiger `Run` spürbar dauern und kosten. `Step size` entsprechend groß wählen, wenn nur eine grobe Tendenz interessiert, oder gezielt mit `Position` auf den relevanten Ausschnitt springen, statt ab `total` zu starten.

Die Kerzennummerierung ist überall konsistent: `#1` = neueste Kerze, `#total` = älteste — genau die Nummerierung, die der Agent selbst beim Referenzieren von Kerzen verwendet (z. B. bei `zone_marker`/`trade_marker`).

---

## 5. Chart-Bereich

Zeigt den Standard-Kerzenchart (gleiche Chart-Komponente wie Chart Analysis) mit:

- Overlay-Indikatoren und Oszillatoren aus dem Analyse-Tab
- Swing-Level-Preislinien aus dem Analyse-Tab
- Vom Agenten gezeichnete Zonen, Trade-Linien und Kerzen-Marker (siehe Abschnitt 11)
- Im Simulation-Tab zusätzlich: ein oranger Pfeil-Marker **„Agent-Grenze"** an der zuletzt sichtbaren Kerze, solange `Position` zwischen `0` und `total` liegt — praktisch, um auf einen Blick zu sehen, wo im Chart der Agent gerade „steht", ohne die Zahlenfelder lesen zu müssen.

Höhe verstellbar über den Ziehgriff darunter (160–800 px) — bei einer Simulation mit vielen Trade-Markierungen lohnt sich ein größerer Chart, um die entstehenden Linien nicht zu übersehen.

---

## 6. Linke Spalte: Chat

Freier Chat mit dem Agenten über den aktuell geladenen Kerzen-Storage.

### 6.1 Kopfleiste

| Element | Funktion |
|---------|---------|
| **→ KB** | Exportiert den gesamten sichtbaren Chatverlauf als Markdown-Dokument in die Knowledgebase. |
| **Delete** (Papierkorb) | Löscht nur den Chatverlauf. Zeichnungen bleiben unberührt (`Clear chart`, Abschnitt 4, ist dafür zuständig). |
| **Farbfeld** | Farbe für ab jetzt neu gezeichnete Annotationen — bereits gezeichnete behalten ihre Farbe. |
| **Reasoning-Effort-Dropdown** | `none` / `low` / `medium` / `high`. Standard `low`, unabhängig vom LLM-Modul. |

**Empfehlung zum Farbfeld:** Bei einem Vergleichstest — z. B. „Frage A mit rot, dieselbe Frage nochmal umformuliert mit blau" — die Farbe vor jedem Durchlauf bewusst ändern. So bleibt am Chart sofort erkennbar, welche Zeichnung zu welcher Frage/Version gehört, ohne im Chatverlauf nachschlagen zu müssen.

**Empfehlung zum Reasoning Effort:** Mit `low` starten. Nur erhöhen, wenn die Antworten oberflächlich wirken oder der Agent bei mehrstufigen Analysen (z. B. „vergleiche die letzten drei Swing-Hochs und leite eine Trendaussage ab") sichtbar Schritte auslässt. Ein pauschal hoher Reasoning Effort für einfache Fragen kostet nur Zeit, ohne die Antwortqualität spürbar zu verbessern.

**Achtung:** Ein Agent kann plausibel klingende, aber falsche Behauptungen über den Chart machen (z. B. eine Kerzennummer falsch nennen). Bei wichtigen Aussagen nachfragen, oder den Agenten explizit bitten, seine Behauptung per `get_annotation`/`candle_marker` am Chart zu belegen statt nur in Prosa zu antworten — siehe Abschnitt 11.

### 6.2 Nachrichtenverlauf

- Nutzer-Nachrichten rechtsbündig, Antworten des Agenten linksbündig, jeweils mit Kopieren-Button.
- Auto-Scroll richtet sich am Anfang einer neuen, langen Antwort aus, statt sie komplett nach oben aus dem Sichtbereich zu schieben — bleibt auch bei nachträglicher Größenänderung des Chat-Bereichs erhalten.

### 6.3 Eingabefeld

`Enter` sendet, `Shift+Enter` fügt einen Zeilenumbruch ein. Der Agent bekommt standardmäßig `calculate_indicator`, `zone_marker`, `trade_marker`, `candle_marker`, `get_annotation` (siehe Abschnitt 11).

**Beispiel-Frage, die die Annotation-Tools sinnvoll nutzt:**

> „Sieh dir die letzten 500 Kerzen an. Markiere mit `zone_marker` jede Zone, in der der Preis mindestens dreimal abgeprallt ist, und erkläre kurz, warum du sie für relevant hältst."

Eine solche Frage zwingt den Agenten, seine Aussage direkt am Chart sichtbar zu machen, statt nur eine Textbeschreibung zu liefern, die man nicht ohne Weiteres prüfen kann.

---

## 7. Linke Spalte: Prompt

Editor für den System-Prompt des Agenten.

| Element | Funktion |
|---------|---------|
| **„— load from agent —"-Dropdown + Load** | Übernimmt System-Prompt (und LLM, falls gesetzt) eines existierenden Agenten aus `system.json5`. |
| **LLM-Dropdown** | Welches LLM-Modul für Chat/Step/Run verwendet wird. `— auto —` nimmt das erste verfügbare Modul. |
| **Editor** | Reiner Text-Editor (Monaco, plaintext). |

**Empfehlung — typischer Entwicklungszyklus für einen Prompt:**

1. Entweder komplett neu schreiben oder mit „load from agent" den Prompt eines bestehenden, ähnlichen Agenten als Ausgangspunkt nehmen.
2. Kleine, gezielte Änderung machen (nicht mehrere Dinge gleichzeitig ändern — sonst ist unklar, welche Änderung welchen Effekt hatte).
3. Im `Chat`-Tab mit 2–3 repräsentativen Fragen testen.
4. Wirkt die Antwort besser/schlechter als vorher? Nächste Änderung.
5. Sobald zufriedenstellend: Preset speichern (Abschnitt 2).

**Achtung — Änderungen hier werden NICHT automatisch live:** Der Prompt-Editor der Workbench ist vollständig getrennt vom System-Prompt des echten Agenten in `system.json5`. Eine Verbesserung, die hier erarbeitet wurde, muss **manuell** in die Agent-Konfiguration (Config → Agent Config) übertragen werden, damit sie im Live-Betrieb wirkt. Es gibt keinen „Übernehmen"-Knopf, der das automatisch erledigt.

---

## 8. Rechte Spalte: Analyse-Tab

Entspricht funktional dem Analyse-Bereich in Chart Analysis — mit einem wichtigen Unterschied: **alles hier Sichtbare wird auch tatsächlich an das LLM übergeben**, nicht nur auf dem Chart angezeigt (siehe Abschnitt 10).

### 8.1 Indikatoren

Gleiches Panel wie in Chart Analysis (EMA, SMA, RSI, ATR, BB, VWAP, SlopeE, SlopeS). Details siehe [Chart Analysis Handbuch](ui.action.chart_analysis.de.md#5-indikatoren--vollständige-erklärung).

### 8.2 Swing Levels

Gleiches Panel wie in Chart Analysis — mit einer Ausnahme: **kein Visible/All-Umschalter.** Swing Levels beziehen sich hier immer ausschließlich auf das sichtbare Kerzenfenster (`Position`).

**Empfehlung — realistisch testen:** Wenn der Prompt am Ende für einen Agenten gedacht ist, der in Produktion bestimmte Indikatoren/Swing Levels sieht, sollten hier **dieselben** Indikatoren mit denselben Einstellungen eingerichtet werden. Testet man den Prompt hier ohne Indikatoren, obwohl der Ziel-Agent später mit EMA(20)/EMA(50) arbeitet, sind die Testergebnisse nicht aussagekräftig — der Agent „sieht" in der PWB schlicht weniger, als er später live sehen wird.

---

## 9. Rechte Spalte: Simulation-Tab

Ein Mini-Snapshot-Designer für Chat/Step/Run: dieselbe `tool_blocks`/`calculation_blocks`/`assembly_transform_script`-Editieroberfläche wie im echten Snapshot Designer, hier zum Testen gegen den geladenen Kerzen-Storage.

| Element | Funktion |
|---------|---------|
| **„— load from snapshot profile —"-Dropdown + Load** | Übernimmt tool_blocks/calculation_blocks/assembly_transform_script eines existierenden Snapshot-Profils. |
| **tool_blocks-Panel** | Gleiche Oberfläche wie im Snapshot Designer, inkl. „Test" pro Zeile. |
| **calculation_blocks-Panel** | „Test" führt alle tool_blocks plus genau diesen einen Rechenblock aus. |
| **assembly_transform_script** | Optionales Zusammenführungs-Skript, gleicher Editor wie im Snapshot Designer. |
| **Auto Trade-Status einfügen** | Fügt jeder Step-Anfrage automatisch einen Text über aktuell offene simulierte Trades hinzu. |
| **FIFO aktivieren** | Wenn aktiv, muss der **älteste** noch offene simulierte Trade zuerst geschlossen werden, bevor `trade_marker` das Schließen eines neueren erlaubt — der Versuch, „außer der Reihe" zu schließen, wird mit einer Fehlermeldung abgelehnt. Bildet Broker nach, die FIFO-Schließung vorschreiben (z. B. bestimmte US-regulierte Konten). Aus ohne diese Einschränkung, entspricht dem Standardverhalten von Hedging-fähigen Brokern. |
| **delete of trades accepted** | Standardmäßig **aus**. Ein bereits aufgezeichneter Trade-Leg gilt als beim Broker ausgeführt und lässt sich normalerweise nicht löschen, nur schließen (siehe Abschnitt 11). Diese Checkbox schaltet `op='delete'` für `trade_marker` gezielt für diese Sitzung frei — z. B. um eine eindeutige Fehlbedienung (falsche Kerze, falsches Tool) zu bereinigen, bevor daraus eine „echte" Order-Historie wird. |
| **Test / Preview** | Baut den kompletten Snapshot einmalig zusammen, ohne das LLM aufzurufen. |

**Wirkung auf Chat/Step/Run:** Sobald hier mindestens ein `tool_block` eingetragen ist, bekommt der Agent den vollständig assemblierten Snapshot statt der rohen Kerzendaten — verankert auf die zuletzt sichtbare Kerze. Bleibt die Liste leer, bekommt der Agent den einfachen Kerzentext-Block aus dem Analyse-Tab.

**Empfehlung — wann welchen Modus nutzen:** Für reines Prompt-Wording-Tuning („klingt die Antwort wie gewünscht?") reicht der einfache Kerzentext-Modus (Simulation-Tab leer lassen) meist aus und ist schneller einzurichten. Sobald es aber darum geht, ob der Prompt mit den **echten** Produktionsdaten eines bestimmten Agenten funktioniert (inkl. aller Tool-Blocks, Berechnungen, Sondertransformationen), unbedingt das passende Snapshot-Profil laden — sonst testet man streng genommen nur die Sprachfähigkeit des LLM, nicht das Zusammenspiel mit der echten Datenpipeline.

**Blockierte Tools:** Handlungs-Tools wie `place_order`, `close_position`, `raise_alarm` sind hier grundsätzlich nicht wählbar — ein Snapshot darf nur Daten sammeln. Die vier Annotation-Tools (Abschnitt 11) sind hier bewusst verfügbar, anders als im echten Snapshot Designer.

---

## 10. Rechte Spalte: LLM-Context-Tab

Zeigt exakt, was der Agent bei der nächsten Chat-Nachricht als Kontext bekommen würde — ohne das LLM aufzurufen, über denselben Code wie ein echter Chat-Aufruf.

| Feld | Bedeutung |
|------|-----------|
| `mode` | `"snapshot"` bei konfigurierten tool_blocks, sonst `"candles"`. |
| `total_candles` / `visible_candles` | Größe des geladenen Fensters bzw. des sichtbaren Ausschnitts. |
| `candles` | Strukturierte Liste der sichtbaren Kerzen — nur zur Anzeige. |
| `indicators` / `swing_levels` | Aktuell sichtbare Indikatoren/Swing Levels. |
| `snapshot` / `snapshot_errors` | Der assemblierte Snapshot samt Fehlern, nur bei konfigurierten tool_blocks. |
| `system_prompt` | Der System-Prompt exakt wie im Prompt-Tab. |
| `question` | Der aktuelle Text im Chat-Eingabefeld. |
| `user_message` | Der exakte Text, den der Agent als User-Message erhält. |

**Empfehlung:** Wenn eine Antwort seltsam oder falsch wirkt, **zuerst hier nachsehen**, bevor man den Prompt oder das LLM verdächtigt. Ein sehr häufiger Grund für „der Agent sieht das nicht" oder „der Agent ignoriert meine Indikatoren" ist schlicht, dass die Daten gar nicht im `user_message`-Text ankommen (z. B. weil ein Indikator im Analyse-Tab deaktiviert ist, oder ein Snapshot-Profil eine unerwartete Fehlermeldung liefert). Dieser Tab beantwortet die Frage „was hat das LLM wirklich bekommen" mit Sicherheit, ohne raten zu müssen.

An das LLM gehen zwei getrennte Nachrichten — die System-Message (1:1 der Prompt-Tab-Inhalt) und die User-Message (`user_message`). Das `candles`-Feld existiert nur für die Anzeige in diesem Tab; die Kerzendaten selbst gehen dem LLM nur einmal zu, im Textblock von `user_message`.

---

## 11. Annotation-Tools des Agenten

Der Agent kann während des Chats vier sandbox-eigene Tools benutzen, um seine Analyse direkt auf dem Chart festzuhalten:

| Tool | Zeichnet | Verwendung |
|------|----------|-----------|
| `zone_marker` | Ein Rechteck über einen Kerzenbereich (z. B. Angebots-/Nachfragezone) | Schreibend |
| `trade_marker` | Einen Ein-/Ausstiegspunkt; zwei zusammengehörige Aufrufe (open/close) ergeben eine Trade-Linie | Schreibend |
| `candle_marker` | Einen Pfeil-Marker über/unter einer einzelnen Kerze mit Freitext | Schreibend |
| `get_annotation` | Sucht eine zuvor gesetzte Markierung samt ihrer echten Kerzendaten anhand ID oder Kerzenbereich | Lesend |

Jeder schreibende Aufruf hat einen Parameter `op` (`new` / `change` / `delete`) — mit einer wichtigen Ausnahme bei `trade_marker`, siehe unten:

- **`new`** — legt eine neue Markierung an, kurze ID (2 Zeichen) als Präfix im Label, z. B. `[A3] Angebotszone`.
- **`change`** — korrigiert eine bestehende Markierung; ersetzt die Zeichnung am Chart statt sie zu verdoppeln.
- **`delete`** — entfernt eine bestehende Markierung.

**Sonderregel bei `trade_marker`: Ein Trade-Leg ist nach `new` unveränderlich.** Ein `open`- oder `close`-Eintrag simuliert eine tatsächlich beim Broker ausgeführte Order — und die lässt sich in der Realität nicht nachträglich korrigieren oder zurücknehmen. Deshalb gilt bei `trade_marker` abweichend von `zone_marker`/`candle_marker`:

- `op='change'` darf bei einem Trade-Leg **nur** das optionale Freitextfeld `note` setzen/ändern — Kerze, Richtung und Aktion (open/close) bleiben wie ursprünglich aufgezeichnet. Ein Änderungsversuch ohne `note` oder mit dem Anspruch, Kerze/Richtung zu ändern, wird abgelehnt.
- `op='delete'` ist bei einem Trade-Leg **standardmäßig gesperrt** und liefert eine erklärende Fehlermeldung („ein bereits aufgezeichneter Trade kann nicht gelöscht, sondern nur geschlossen werden"). Ein offener Trade lässt sich normalerweise ausschließlich per `action='close'` beenden, niemals rückwirkend entfernen — es sei denn, die Checkbox **„delete of trades accepted"** im Simulation-Tab (Abschnitt 9) ist für diese Sitzung explizit aktiviert.

Das ist genau die Korrektur, die verhindert, dass ein Agent seinen ursprünglichen Einstieg im Nachhinein „schöner" umschreibt (Rückblick-Bias) — jeder Trade-Eintrag bleibt als ehrlicher Verlaufsdatensatz stehen.

**Richtung sichtbar auf beiden Legs:** `direction` (long/short) wird nicht nur beim `open`-Leg gespeichert, sondern automatisch auch auf den zugehörigen `close`-Leg übertragen — im Chart-Label steht sie explizit als Text (`LONG`/`SHORT`), nicht nur implizit über die Pfeilrichtung des Open-Markers.

**Nützliches Muster:** Den Agenten explizit bitten, seine eigenen Markierungen zu überprüfen und ggf. zu korrigieren, z. B.:

> „Prüfe deine bisherigen Zonen-Markierungen noch einmal gegen die echten Kerzendaten (nutze `get_annotation`) und korrigiere jede, die nicht mehr stimmt."

Das nutzt genau die Kombination aus lesendem (`get_annotation`) und schreibendem (`zone_marker` mit `op=change`) Tool, für die diese vier Tools gebaut wurden — der Agent muss sich dabei an echten Daten überprüfen, nicht nur aus dem Gedächtnis antworten.

Annotationen werden client-seitig über die gesamte Sitzung gesammelt und bei jeder Anfrage als `existing_annotations` mitgeschickt. `Clear chart` (Abschnitt 4) leert diese Sammlung.

---

## 12. Frozen-Window-Prinzip: warum das wichtig ist

Die Workbench ist bewusst so gebaut, dass der geladene Chart die einzige Datenquelle für die gesamte Sitzung bleibt — das ist kein Implementierungsdetail, sondern der Grund, warum die PWB als Testwerkzeug überhaupt taugt:

- **Reproduzierbarkeit:** Ohne einen fixen Anchor würde jede Chat-Anfrage automatisch die neuesten Live-Daten abfragen. Zwei Fragen im Abstand von 10 Minuten würden dann leicht unterschiedliche Kerzenfenster sehen — ein Vergleich zweier Prompt-Antworten wäre nicht mehr aussagekräftig, weil sich zwischen den beiden Tests auch die Datenbasis geändert hat.
- **Vergleichbarkeit zwischen Prompt-Varianten:** Weil das Fenster eingefroren ist, kann man Prompt A und Prompt B nacheinander exakt gegen dieselben Kerzen testen und die Antworten fair vergleichen.
- Direkte Tool-Aufrufe des Agenten (`calculate_indicator`, `get_candles`, `get_swing_levels`) bekommen den Zeitpunkt der zuletzt sichtbaren Kerze erzwungen als `start`-Parameter — der Agent kann nicht versehentlich außerhalb des sichtbaren Fensters nachschauen.
- Ein Anchor-Datum in der Kerzenlade-Leiste bestimmt nur, welches Fenster geladen wird — danach gilt dasselbe Prinzip.

---

## 13. Häufige Probleme

**Problem: Der Agent antwortet leer oder bricht scheinbar grundlos ab.**
Ursache meist: zu kleines Token-Budget bei großem Kerzenfenster plus hohem Reasoning Effort — das Modell verbraucht sein internes Denk-Budget, bevor es zu einer sichtbaren Antwort kommt. Lösung: Kerzenanzahl reduzieren, Reasoning Effort senken, oder ein Modell mit größerem Kontextfenster wählen.

**Problem: Der Agent scheint die eingestellten Indikatoren oder Swing Levels zu ignorieren.**
Zuerst den `LLM-Context`-Tab öffnen (Abschnitt 10) und prüfen, ob die Daten überhaupt in `user_message` auftauchen. Häufigste Ursache: der Indikator ist im Analyse-Tab per Auge-Icon ausgeblendet — ausgeblendete Indikatoren werden nicht an das LLM übergeben, auch wenn sie im Chart-Panel noch als Eintrag sichtbar sind.

**Problem: Kerzenzahlen/-nummern scheinen sich zwischen zwei Nachrichten zu verschieben.**
Prüfen, ob zwischendurch `Load` erneut geklickt oder eine der Einstellungen in der Kerzenlade-Leiste geändert wurde (das löst automatisch ein `Load` aus und setzt damit einen neuen Anchor). Innerhalb einer Sitzung ohne erneutes Laden bleibt die Nummerierung stabil.

**Problem: `Run` scheint zu hängen.**
Jeder Schritt ist ein echter, synchroner LLM-Aufruf — bei großen Kerzenfenstern, hohem Reasoning Effort oder einem langsamen LLM-Provider kann ein einzelner Schritt mehrere Sekunden dauern. Im Chatverlauf erscheint währenddessen „Waiting for the agent…". Vor einem Abbruch-Verdacht: `Stop` klicken, kurz warten, und mit kleinerem Kerzenfenster oder größerer `Step size` erneut versuchen.

**Problem: Eine im Prompt-Tab erarbeitete Verbesserung wirkt sich nicht auf den Live-Agenten aus.**
Kein Bug — siehe Abschnitt 7: der PWB-Prompt muss manuell in die Agent Config übertragen werden.

---

## 14. Ausführliches Beispiel: einen Prompt von Grund auf entwickeln

Ziel: einen Agenten entwickeln, der wie der bekannte Devisenhändler Andrew Krieger traden soll — aggressiv, positionsstark, mit klarem Fokus auf Liquiditätsungleichgewichte.

1. **Kerzen laden:** Pair und Timeframe wählen (z. B. `EUR_USD`, `M15`), Kerzenanzahl auf 500 setzen, `Load` klicken.
2. **Prompt schreiben** (`Prompt`-Tab), grob:
   > „Du handelst im Stil von Andrew Krieger: aggressiv, überzeugt von großen, asymmetrischen Positionen, fokussiert auf strukturelle Liquiditätsungleichgewichte statt kurzfristigem Rauschen. Analysiere die letzten 500 Kerzen als Ganzes — nicht nur die letzten 150 — und markiere mit `trade_marker`, wo du eingestiegen wärst und wo du den Trade beendet hättest."
3. **Erste Testfrage** im `Chat`-Tab: „Analysiere den Chart und zeige deinen Trade-Setup."
4. **Antwort prüfen:** Bezieht sich der Agent tatsächlich auf ältere Kerzen, oder nur auf die letzten paar? Falls nur auf die letzten paar — im Prompt noch expliziter machen, dass das *gesamte* geladene Fenster relevant ist (ein häufiges Verhalten: LLMs neigen dazu, sich auf die zuletzt gezeigten/nummerierten Daten zu konzentrieren, wenn nicht ausdrücklich anders verlangt).
5. **Iterieren:** Formulierung anpassen, erneut fragen, bis das Verhalten passt.
6. **Simulation:** `Position` auf `total` setzen, `Step size` auf z. B. 20, `Run` klicken, und beobachten, ob der Agent über die ganze Zeitreihe hinweg konsistent im beschriebenen Stil bleibt.
7. **Sichern:** Preset unter `andrew_krieger_v1` speichern, sobald das Verhalten überzeugt.

---

## 15. Weitere Arbeitsabläufe

### 15.1 Eine Handelsstrategie über eine Zeitreihe simulieren

1. `Position` auf einen Wert größer 0 setzen (z. B. `total`).
2. `Step size` festlegen — kleiner für feingranulare Beobachtung, größer für einen schnellen Überblick über den Gesamttrend.
3. Optional im `Simulation`-Tab ein Snapshot-Profil laden, damit der Agent denselben Kontext wie im Live-Betrieb bekommt (siehe Empfehlung in Abschnitt 9).
4. Erst `Step` ein paar Mal, dann `Run` klicken.
5. Nach Abschluss die entstandenen Trade-Linien auf dem Chart und im Chatverlauf auswerten — insbesondere, ob geschlossene Trades in Summe eher gewinnbringend oder verlustreich waren, und ob die Begründungen des Agenten nachvollziehbar sind.

### 15.2 Zwei Prompt-Varianten fair vergleichen

1. Kerzen einmal laden (nicht zwischendurch neu laden — sonst ändert sich die Vergleichsbasis).
2. Prompt A eintragen, Annotationsfarbe auf z. B. Rot setzen, Testfrage stellen.
3. Preset unter `test_a` speichern.
4. `New` **nicht** verwenden (löscht die geladenen Kerzen) — stattdessen im Prompt-Tab direkt Prompt B eintragen, Annotationsfarbe auf Blau ändern, dieselbe Frage erneut stellen.
5. Antworten und Chart-Markierungen (rot vs. blau) nebeneinander vergleichen.

### 15.3 Die aktuelle Sitzung als Preset sichern

1. Oben im Namensfeld einen Namen eintragen.
2. `Save` klicken.
3. Zu einem späteren Zeitpunkt denselben Namen auswählen und `Load` klicken — Kerzen danach erneut per `Load` laden, da sie nicht Teil des Presets sind.
