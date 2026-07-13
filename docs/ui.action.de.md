[Zurück zum UI-Handbuch](ui.de.md)

# Action

Der Bereich `Action` ist der operative Arbeitsbereich von OpenForexAI. Er ist die primäre Oberfläche, die während des Live-Handels genutzt wird — um System-Aktivitäten zu überwachen, Positionen zu prüfen, KI-Entscheidungen einzusehen und direkt mit Agenten zu interagieren.

## Unterseiten

- [Initial](ui.action.initial.de.md) — System-Status und Laufzeit-Steuerung
- [Agent Chat](ui.action.chat.de.md) — Direkte KI-Agenten-Interaktion und Inspect-Runs
- [Orderbook](ui.action.orderbook.de.md) — Offene Positionen, Trade-Verlauf und P&L
- [Chart Analysis](ui.action.chart_analysis.de.md) — Visueller Chart mit KI-Analyse-Overlay

---

## Initial

`Initial` ist die Start-, Status- und Laufzeitseite.

Typische Zwecke:

- lokale Version und Update-Status prüfen
- Broker-Konnektivität prüfen
- LLM-Konnektivität prüfen
- sehen, ob die Runtime pausiert oder aktiv ist
- aktivierte Agenten sehen
- Update, Pause, Resume oder Neustart auslösen

Die `Initial`-Seite ist der erste Anlaufpunkt nach dem Start von OpenForexAI. Vor dem Aktivieren des Live-Handels sollte sichergestellt werden, dass alle Konnektivitätsindikatoren grün sind:

- **Broker-Status**: verbunden mit MT5 oder OANDA; empfängt Kerzendaten
- **LLM-Status**: verbunden mit dem konfigurierten LLM-Provider; antwortet auf Testaufrufe
- **Agenten-Status**: alle konfigurierten Agenten als aktiv aufgelistet
- **Runtime-Status**: System als laufend angezeigt (nicht pausiert)

Ist ein Indikator rot oder gelb, sollte das Problem vor dem Live-Trading behoben werden. Häufige Ursachen:

- Broker-Verbindung verloren: Netzwerk, Broker-Server-Status und API-Zugangsdaten in [Broker Modules](ui.config.broker_modules.de.md) prüfen
- LLM antwortet nicht: API-Schlüssel und Endpunkt in [LLM Modules](ui.config.llm_modules.de.md) verifizieren
- Keine Agenten aktiv: [Agent Config](ui.config.agent_config.de.md) prüfen

### Laufzeit-Steuerung

Die `Initial`-Seite bietet Schaltflächen zur Steuerung der Runtime:

| Schaltfläche | Auswirkung |
|--------------|------------|
| Pause | Alle Agentenaktivitäten anhalten; keine neuen Analysen oder Trades werden ausgelöst |
| Resume | Agentenaktivitäten nach einer Pause wieder aktivieren |
| Restart | Die vollständige Runtime stoppen und neu starten (nützlich nach Konfigurationsänderungen) |
| Update | Neueste Version laden und neu starten |

Das Pausieren ist nützlich, wenn Konfigurationsänderungen vorgenommen werden sollen, ohne während des Übergangs Trades auszulösen. Immer pausieren, bevor wesentliche Änderungen an Agent Config oder Event Routing vorgenommen werden.

Vorgesehener Screenshot:
- [Initial-Seite mit Runtime-Status](image/ui-02-initial-runtime-status.png)

---

## Agent Chat

`Agent Chat` ist sowohl ein normaler Agentenchat als auch eine kontrollierte Ausführungsoberfläche für Inspect-Runs.

Was du dort tun kannst:

- Agent auswählen
- normale Nachricht schreiben und `Send` klicken
- `Execute` klicken, um den gewählten Agenten im Inspect-Modus zu starten
- kompletten sichtbaren Chatverlauf als Markdown exportieren
- aktuellen Chatverlauf leeren

### Chat-Modus vs. Execute-Modus

**Chat-Modus** (`Send`): sendet deine Nachricht als normale User-Message an den Agenten. Der Agent antwortet mit seinem konfigurierten System-Prompt. Nützlich, um dem Agenten Fragen zu stellen, seinen aktuellen Status abzufragen oder über Marktbedingungen zu diskutieren.

**Execute-Modus** (`Execute`): führt einen vollständigen strukturierten Agentenzyklus im Inspect-Modus aus. Für AA-Agenten wird dadurch ein vollständiger Snapshot-Build, LLM-Aufruf und Analyse ausgelöst — genau wie im Live-Trading, aber mit vollständiger Einsicht in jeden Schritt. Das rechte Panel wird mit technischen Inspektionsdaten gefüllt.

Typischer Ablauf:

1. `Agent Chat` öffnen.
2. Gewünschten Agenten auswählen.
3. Text in das Eingabefeld schreiben.
4. `Send` für eine normale Nachricht oder `Execute` für einen strukturierten Testlauf verwenden.
5. Den sichtbaren Verlauf links lesen.
6. Die technischen Details rechts und unter dem Chart prüfen.

Bei BA-Agenten kann ein AA-Analyseergebnis in das Eingabefeld eingefügt und dann per `Execute` getestet werden.

### Wann Agent Chat eingesetzt wird

- Vor dem Live-Betrieb: Execute auf dem AA-Agenten ausführen, um Snapshot und LLM-Antwort zu prüfen
- Trade debuggen: Execute ausführen, um die Bedingungen zu reproduzieren, die zu einem Signal geführt haben
- Prompt-Änderungen testen: nach dem Aktualisieren eines Decision-Prompt-Profils Execute ausführen, um zu prüfen, dass das LLM den neuen Prompt erhält und korrekt antwortet
- BA-Agent-Verifikation: eine Beispiel-Analyse als JSON einfügen und Execute ausführen, um zu prüfen, dass der BA-Agent den Trade korrekt platzieren würde

Vorgesehene Screenshots:
- [Agent Chat Übersicht](image/ui-03-agent-chat-overview.png)
- [Agent Chat Execute-Lauf mit sichtbarem Verlauf](image/ui-04-agent-chat-execute-run.png)

---

## Agent-Chat-Inspector

Wenn der gewählte Agent ein AA ist, zeigt die rechte Seite einen Chart und darunter einen technischen Inspektionsbereich.

Dort erscheinen:

- ein Candle-Chart
- optional persistierte Analysemarker
- Timeframe-Buttons wie `M5`, `M15`, `M30`, `H1`
- ein Inspector unterhalb des Charts

Die aktuellen Inspector-Tabs sind:

- `Overview`
- `Snapshot`
- `LLM`
- `Tools`
- `Runtime`

Diesen Bereich verwendest du, wenn du verstehen willst, was während eines `Execute`-Laufs technisch passiert ist, ohne den Chat selbst zu überladen.

### Overview-Tab

Zeigt eine Zusammenfassung des letzten Execute-Laufs:
- Signalrichtung (BUY / SELL / NO SIGNAL)
- Konfidenzwert
- Entry-, Stop-Loss- und Take-Profit-Level
- Begründungszusammenfassung des LLM
- etwaige Validierungsfehler

### Snapshot-Tab

Zeigt das vollständige Snapshot-Dict, das assembliert und an das LLM übergeben wurde. Das ist die genaue Datenstruktur, die das LLM als User-Message erhalten hat. Diesen Tab verwenden, um:
- zu prüfen, dass alle erwarteten Datenblöcke vorhanden sind
- zu prüfen, dass Werte (ATR, Swing-Levels, Session-Kontext) korrekt sind
- unerwartetes LLM-Verhalten auf die Daten zurückzuverfolgen

### LLM-Tab

Zeigt:
- den System-Prompt (nach Decision-Prompt-Substitution)
- die User-Message (assemblierter Snapshot)
- die rohe LLM-Antwort
- Token-Verbrauch (Input-Tokens, Output-Tokens, Kostenschätzung)

Das ist das definitive Prüfprotokoll, was das LLM gefragt wurde und was es gesagt hat.

### Tools-Tab

Zeigt alle Tool-Aufrufe des Laufs in chronologischer Reihenfolge:
- Tool-Name und Eingabeparameter
- Tool-Antwort
- Timing je Aufruf

Einsetzen, wenn die Snapshot-Assembly benutzerdefinierte Tools verwendet und prüfen werden soll, ob sie die erwarteten Daten zurückgegeben haben.

### Runtime-Tab

Zeigt Timing-Daten für jede Phase des Execute-Zyklus:
- Dauer der Snapshot-Assembly
- Dauer des LLM-Aufrufs
- Dauer des Response-Parsings
- Gesamtzykluszeit

Einsetzen, um Performance-Engpässe oder unerwartete Langsamkeit zu identifizieren.

Typische Prüfobjekte:

- der gebaute Snapshot
- der finale LLM-Input und Output
- Tool-Aufrufe und Tool-Ergebnisse
- Timing-Daten
- Token-Verbrauch
- Validierungsfehler

Vorgesehene Screenshots:
- [Agent Chat Inspector Overview-Tab](image/ui-05-agent-chat-inspector-overview.png)
- [Agent Chat Snapshot-Tab](image/ui-06-agent-chat-snapshot-tab.png)
- [Agent Chat LLM-Tab](image/ui-07-agent-chat-llm-tab.png)
- [Agent Chat Tools-Tab](image/ui-08-agent-chat-tools-tab.png)

---

## Orderbook

Die Seite `Orderbook` dient zur operativen Prüfung von Order-Einträgen in Verbindung mit Analysekontext.

Was du dort tun kannst:

- offene, geschlossene und abgelehnte Einträge prüfen
- Start- und Endzeitpunkte vergleichen
- Close-Grund und verknüpfte Analyse sehen
- den Detaildialog eines Eintrags öffnen

### Trade-Eintrag-Status

| Status | Bedeutung |
|--------|-----------|
| Open | Position ist beim Broker aktiv |
| Closed | Position wurde geschlossen; finales P&L erfasst |
| Rejected | Signal wurde erzeugt, aber vom EC Relay blockiert |
| Pending | Order platziert, aber noch nicht vom Broker bestätigt |

### Zeitstempel-Verhalten

Wichtiges aktuelles Verhalten:

- brokerbestätigte Zeitstempel werden bevorzugt angezeigt
- wenn brokerseitige Zeitstempel noch fehlen, wird ein lokaler UTC-Fallback angezeigt
- unbestätigte Brokerdaten werden optisch markiert

Dadurch kannst du unterscheiden zwischen:

- einem brokerbestätigten Datensatz
- einem vorläufigen lokalen Datensatz, der noch auf Brokerbestätigung wartet

### Detaildialog

Einen Eintrag anklicken, um den Detaildialog zu öffnen. Der Dialog zeigt:

- vollständige Trade-Parameter (Entry, SL, TP, Lotgröße, Richtung)
- die Analyse, die den Trade ausgelöst hat (Signal, Konfidenz, Begründung)
- den Snapshot-Kontext zum Einstiegszeitpunkt
- Öffnungs-/Schließzeitpunkte und Dauer
- realisiertes P&L in Kontowährung und Pips

Die verknüpfte Analyseansicht zeigt genau, was das LLM gesagt hat, als es das Signal erzeugt hat. Das ist für die Post-Trade-Analyse unerlässlich: Bei einem verlustbringenden Trade kann geprüft werden, ob das LLM-Reasoning fundiert war oder ob das Signal hätte gefiltert werden sollen.

### Orderbook filtern

Mit den Filtersteuerungen oben auf der Seite die Ansicht eingrenzen:

- nach Status filtern (open / closed / rejected / pending)
- nach Symbol filtern (EURUSD, GBPUSD usw.)
- nach Agent filtern
- nach Zeitbereich filtern
- nach Richtung filtern (BUY / SELL)

Vorgesehene Screenshots:
- [Orderbook Übersicht mit bestätigten und vorläufigen Einträgen](image/ui-09-orderbook-overview.png)
- [Orderbook Detaildialog](image/ui-10-orderbook-entry-detail.png)

---

## Chart Analysis

Die Seite `Chart Analysis` zeigt einen visuellen Candlestick-Chart für jedes konfigurierte Symbol mit eingeblendeten KI-Analyseergebnissen.

Was sichtbar ist:

- Live-Candlestick-Chart für das gewählte Symbol und den gewählten Zeitrahmen
- Buy-/Sell-Signal-Marker an den Kerzen, bei denen Analysen ausgelöst wurden
- Swing-High-/-Low-Marker aus den Snapshot-Daten
- Trendrichtungs-Overlay
- ATR-Bänder oder Stop-Loss-Visualisierung

`Chart Analysis` verwenden, um:

- die Qualität der jüngsten Signale visuell zu beurteilen
- Muster bei Ein- und Ausstiegen des Systems zu erkennen
- zu prüfen, ob das System dem vorherrschenden Trend folgt oder dagegen handelt
- zu validieren, dass die Swing-Level-Erkennung korrekt funktioniert

Vorgesehene Screenshots:
- [Chart Analysis mit Signal-Markern](image/ui-11-chart-analysis-signals.png)
- [Chart Analysis Swing-Levels-Overlay](image/ui-12-chart-analysis-swing-levels.png)
