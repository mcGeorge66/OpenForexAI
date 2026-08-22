[Zurück zu Action](ui.action.de.md)

# Orderbook — Handbuch

Das **Orderbook** ist die vollständige Handelshistorie und Inspektionsseite für alle von OpenForexAI verwalteten Positionen. Es zeigt eine strukturierte Tabelle aller Orders — offen, geschlossen, abgelehnt und storniert — zusammen mit einem verknüpften Chart, das den Marktkontext des ausgewählten Trades zeigt. Zusätzlich stehen pro Zeile vier Werkzeuge zur Verfügung: die gespeicherte AA-Analyse öffnen, den Event-Trace ansehen, eine KI-Chat-Untersuchung starten und der Order in der vollständigen Chart-Analyse öffnen. Das Orderbook ist bewusst **reine Inspektion** — Trades werden hier nicht platziert, geändert oder geschlossen; dafür nutzen Sie die Broker-Plattform direkt oder Agent Chat / Initial.

---

## Inhaltsverzeichnis

1. [Seitenaufbau](#1-seitenaufbau)
2. [Filterleiste](#2-filterleiste)
3. [Trade-Tabelle — Spalten](#3-trade-tabelle--spalten)
4. [Aktionen pro Zeile: Open, Trace, AI, Chart](#4-aktionen-pro-zeile-open-trace-ai-chart)
5. [Schließgründe im Detail](#5-schließgründe-im-detail)
6. [Trade-Detail-Chart](#6-trade-detail-chart)
7. [Chart-Steuerung](#7-chart-steuerung)
8. [AA-Analyse- und Recommendation-Popup](#8-aa-analyse--und-recommendation-popup)
9. [Print und Knowledgebase-Export](#9-print-und-knowledgebase-export)
10. [Typische Arbeitsabläufe](#10-typische-arbeitsabläufe)
11. [Szenarien und Beispiele](#11-szenarien-und-beispiele)
12. [Schnellreferenz](#12-schnellreferenz)
13. [Häufige Fragen](#13-häufige-fragen)

---

## 1. Seitenaufbau

Die Seite ist vertikal in zwei Bereiche geteilt, getrennt durch eine verschiebbare Trennlinie:

```
┌─────────────────────────────────────────────────────────────────┐
│  FILTER: [alle] [offen] [geschlossen] [abgelehnt]  Max: [__]    │
│          [Refresh] [Print] [→ KB]                                │
├───────────────────────────────────────────────────────────────────┤
│  TRADE-TABELLE                                                   │
│  Pair | Von | Bis | HH:MM | Id | Units | Stake | Ergebnis |     │
│  Close | Analysis: [Open] [Trace] [AI] [Chart]                   │
├══════════════════════ TRENNLINIE ═══════════════════════════════╡
│  TRADE-DETAIL-CHART                                              │
│  Info-Boxen: Entry/Exit · SL/TP · Support/Resistance · Indikat. │
│  [Show the Analyses] [M5] [M15] [M30] [H1]                       │
│  Chart mit Kerzen + Entry/Exit/SL/TP-Linien + Start/End-Marker   │
└─────────────────────────────────────────────────────────────────┘
```

Ein Klick auf eine Zeile wählt den Trade aus und lädt den zugehörigen Chart unten. Tabelle und Chart bleiben synchron. Die Trennlinie kann zwischen 28 % und 72 % der Seitenhöhe verschoben werden (kleiner Griff in der Mitte der Linie) — die Aufteilung wird nicht gespeichert und setzt sich bei jedem Öffnen der Seite auf etwa 50/50 zurück.

Das Auswählen einer Zeile navigiert **nicht** weg vom Orderbook — der eingebettete Chart unten ist eine schlanke, reine Vorschau. Für tiefere technische Analyse (eigene Indikatoren, Swing Levels, Zeichenwerkzeuge) nutzen Sie den **Chart**-Button (Abschnitt 4), um denselben Trade in der vollständigen Chart-Analyse zu öffnen.

---

## 2. Filterleiste

Die Filterleiste befindet sich oben auf der Seite und steuert, welche Einträge geladen und in der Tabelle angezeigt werden.

### 2.1 Status-Filter

Es gibt genau **vier** Filter-Buttons — es gibt **keinen** eigenen Button für stornierte Trades (siehe unten):

| Filter | Bedeutung |
|--------|-----------|
| **alle** | Zeigt alle Trade-Einträge unabhängig vom Status. Standard nach dem Öffnen der Seite. Einziger Weg, um `CANCELLED`-Einträge zu sehen. |
| **offen** | Zeigt Positionen mit Status `PENDING` (übermittelt, noch nicht bestätigt), `OPEN` (voll bestätigt) **oder** `PARTIALLY_FILLED` — alle drei zusammen, nicht nur voll offene Positionen. |
| **geschlossen** | Zeigt abgeschlossene Positionen, unabhängig vom konkreten Schließgrund (SL, TP, Trailing Stop, Agent-Schließung, Broker-Zwangsschließung oder Sync-Erkennung). |
| **abgelehnt** | Zeigt Einträge, bei denen die Order-Übermittlung an den Broker abgelehnt wurde, bevor die Position je existierte. |

**Wichtig:** Es gibt in der UI **keinen** Button „storniert"/„cancelled". Trades mit Status `CANCELLED` (Entscheidung getroffen, Order gebaut, aber nie an den Broker gesendet — z. B. weil das System zwischen Entscheidung und Ausführung suspendiert wurde, oder ein Duplikat-Guard ausgelöst hat) sind ausschließlich über den Filter **alle** sichtbar, indem Sie in der Close-Spalte nach `CANCELLED` suchen. Wenn Sie prüfen wollen, warum ein erwarteter Trade fehlt: zuerst **abgelehnt**, dann **alle** durchsuchen — nicht davon ausgehen, dass es einen dedizierten Filter dafür gibt.

### 2.2 Max Orders

Das **Max Orders**-Feld begrenzt die Anzahl der geladenen Einträge. Die Änderung wird erst beim Verlassen des Feldes (Blur) oder mit Enter übernommen — reines Eintippen lädt noch nichts neu.

- **Minimum:** 1 (kleinere Werte werden automatisch angehoben)
- **Kein festes Maximum**, aber sehr hohe Werte verlangsamen das Laden
- **Standardwert beim Öffnen der Seite: 7.** Das ist bewusst klein — die Seite lädt schnell und zeigt nur die letzten paar Trades. Erhöhen Sie den Wert sofort, wenn Sie eine echte Review-Session statt eines schnellen Blicks auf die letzten Aktivitäten machen wollen.

Für die tägliche Kontrolle reicht der Standardwert oder ein leicht erhöhter Wert (z. B. 20). Für eine vollständige historische Analyse auf 200–500 oder mehr erhöhen.

### 2.3 Refresh-Button

Der **Refresh**-Button lädt die Tabelle neu und erzwingt dabei zusätzlich einen **Broker-Sync** für jede in der Tabelle vorkommende Kombination aus Broker und Pair, bevor die lokale Datenbank erneut gelesen wird. Das bedeutet: Refresh kann merklich länger dauern als ein reines Neuladen — es fragt aktiv jede relevante Broker-Verbindung nach dem aktuellen Stand ab, statt nur lokale Daten neu zu lesen. Ein Spinner-Icon zeigt den Ladevorgang an.

**Wann Refresh verwenden:** nach einem vermuteten neuen Trade, der noch nicht in der Tabelle erschienen ist, oder wenn Sie vermuten, dass der lokale Status einer Position vom Broker-Stand abweicht.

### 2.4 Print-Button

Erzeugt sofort einen druckfertigen Report für den aktuell ausgewählten Trade. Nur aktiv, wenn ein Trade ausgewählt ist. **Es gibt hier keinen Optionen-Dialog** mit Checkboxen (diesen Dialog gibt es nur bei der Print-Funktion der Chart-Analyse, nicht im Orderbook) — ein Klick auf Print schließt immer alles ein. Details in Abschnitt 9.

### 2.5 → KB-Button

Exportiert den ausgewählten Trade als formatiertes Markdown-Dokument direkt in die Knowledgebase, in einen automatisch verwalteten „Import"-Ordner, mit einem Titel wie `Orderbook_2026-08-21T14-32-10`. Ebenfalls nur aktiv bei ausgewähltem Trade. Details in Abschnitt 9.

---

## 3. Trade-Tabelle — Spalten

Jede Zeile repräsentiert einen Trade-Eintrag. Ein Klick auf eine Zeile wählt sie aus und lädt den zugehörigen Chart.

### Pair

Zeigt in der ersten Zeile das **Währungspaar** (z. B. `EUR_USD`), in der zweiten Zeile **Richtung** (`BUY`/`SELL`) und **Status**.

Wenn der Eintrag noch nicht vom Broker bestätigt wurde, erscheint ein **Warnsymbol** neben dem Pair. Dies ist ein normaler, kurzfristiger Zustand — löst sich typischerweise innerhalb von Sekunden auf. Bleibt es länger als eine Minute bestehen, die Broker-Verbindung auf der Initial-Seite prüfen.

### Von (From)

Der **Öffnungszeitpunkt** — der vom Broker bestätigte `opened_at`-Wert, falls vorhanden, sonst der lokal erfasste `requested_at`-Wert.

- **Gelb/amber:** Es liegt noch kein bestätigter `opened_at`-Wert vor, nur die lokale Anfragezeit. Löst sich nach Broker-Bestätigung auf.
- **Normal:** Vom Broker bestätigt und maßgeblich.

Tipp: Ein gelber Zeitstempel bei einem längst geschlossenen Trade deutet meist darauf hin, dass die Broker-Bestätigung für die Eröffnung nie empfangen oder nie zurücksynchronisiert wurde — lohnt einen direkten Abgleich mit der Broker-Plattform.

### Bis (To)

Der **Schließzeitpunkt**. Bei offenen Positionen leer. Bei `REJECTED`- oder `CANCELLED`-Einträgen (die nie einen echten Schließzeitpunkt hatten) wird hier derselbe Wert wie in „Von" angezeigt, damit die Zeile nicht mit zwei Strichen unvollständig wirkt.

Gleiche Farbcodierung wie „Von": Gelb bedeutet, es liegt nur ein lokal erfasster „Close angefordert"-Zeitstempel ohne bestätigtes `closed_at` vor.

### Dauer (HH:MM)

Die Dauer der Position, berechnet von „Von" bis „Bis".

- `00:15` — 15 Minuten
- `04:32` — 4 Stunden 32 Minuten
- `—` — noch kein „Bis"-Zeitstempel (Position offen); die Dauer wird **nicht** live für offene Positionen berechnet — ein Refresh ist nötig, um sie zu aktualisieren.

### Id

Die **Broker-Order-ID** in Monospace-Schrift. Zeigt `-`, solange noch keine Broker-ID zugewiesen wurde.

### Units

Die **Positionsgröße** in Einheiten der Basiswährung, mit Tausendertrennzeichen formatiert (z. B. `10,000`). Wird vom BA-Agent basierend auf der konfigurierten Positionsgrößen-Logik berechnet.

### Stake

**Dies ist ein Dollarbetrag, keine Prozentangabe.** Die Spalte zeigt `stake_estimate` — den nominalen Positionswert, berechnet als Eröffnungs-Referenzpreis mal Units — mit zwei Dezimalstellen und einem abschließenden `$` (z. B. `12.345,67 $`).

**Achtung, Formatierungs-Falle:** Der Wert wird im Code immer im deutschen Zahlenformat gerendert (Punkt als Tausendertrennzeichen, Komma als Dezimaltrennzeichen) — unabhängig davon, welche Sprache die restliche UI gerade verwendet. `12.345,67 $` bedeutet also zwölftausenddreihundertfünfundvierzig Dollar und 67 Cent.

Lesen Sie diese Spalte **nicht** als „Risiko in % vom Eigenkapital" — dafür müssten Sie SL-Abstand und Units selbst zum Kontostand in Relation setzen; die Stake-Spalte allein sagt das nicht aus.

### Ergebnis (Result)

Der Gewinn oder Verlust in Kontowährung, auf zwei Dezimalstellen.

- **Grün:** Ergebnis ≥ 0
- **Rot:** Ergebnis < 0
- `—`: bei offenen Positionen (kein Live-P&L in dieser Spalte — dafür Broker-Plattform oder GA-Monitor prüfen) oder bei abgelehnten/stornierten Trades, für die nie eine Position existierte.

### Close (Schließgrund)

Der Grund, warum der Trade geschlossen wurde, oder — falls kein Grund gespeichert ist — ein Status-Fallback-Text. Siehe Abschnitt 5 für die exakten Werte. Unter dem Hauptwert steht eine zweite Zeile mit dem gespeicherten Freitext-Schließgrund, oder — falls keiner gespeichert ist — dem Status als Wiederholung.

### Analysis

Vier kleine Aktions-Buttons: **Open**, **Trace**, **AI** und **Chart**. Jeder öffnet ein anderes Werkzeug für genau diesen Trade — siehe nächster Abschnitt für die Details und wann welcher Button der richtige ist.

---

## 4. Aktionen pro Zeile: Open, Trace, AI, Chart

Alle vier Buttons beantworten im weiteren Sinne „erzähl mir mehr über diesen Trade" — aber jeweils eine andere Art von Frage. Die richtige Wahl spart Zeit.

### Open (Dokument-Symbol) — AA-Analyse-Popup

Öffnet ein Popup mit dem vollständigen, gespeicherten Analysetext des AA-Agents zu diesem Trade — unverändert, ohne weitere Werkzeugaufrufe. Der schnellste Weg, um wortgetreu zu lesen, was die Analyse tatsächlich gesagt hat. Details in Abschnitt 8.

**Verwenden, wenn:** Sie eine konkrete Frage haben, deren Antwort wörtlich im Analysetext steht (z. B. „welchen Setup-Typ hat die Analyse hier genannt?").

### Trace (Verzweigungs-Symbol, grün) — Event-Trace-Ansicht

Öffnet die kausale Event-Kette zu diesem Trade: Zuerst wird nach einem Event mit passender `correlation`-ID gesucht; falls keines gefunden wird, fällt die Suche zurück auf einen Scan der letzten `order_request`/`order_placed`-Events nach einem Payload-Treffer. Danach wird derselbe TraceViewer angezeigt, der auch an anderer Stelle im System verwendet wird.

**Verwenden, wenn:** Sie den technischen Ablauf verstehen wollen — welcher Agent hat gefeuert, welche Events wurden in welcher Reihenfolge publiziert, hat ein Guard oder EC eingegriffen — statt der Handelslogik selbst. Kann kein Event aufgelöst werden (z. B. weil der Trade älter ist als das Event-Logging, oder es sich um einen synthetischen/nachgetragenen Eintrag handelt), erscheint eine explizite „kein Event gefunden"-Meldung statt einer leeren Ansicht.

### AI (Roboter-Symbol, indigo) — „Ask AI"-Untersuchungs-Chat

Öffnet ein freischwebendes (verschiebbares, größenveränderbares) Chat-Fenster mit einem echten Tool-Calling-Agent, der bereits den vollständigen Datensatz dieses Trades kennt (AA-Analyse, P&L, Schließbegründung). Anders als ein statisches Popup kann der Agent während des Gesprächs aktiv weitere Daten abrufen — Event-Trace, die live laufende Agent-/EC-Konfiguration, EC-Run-Historie, Marktkerzen/Indikatoren/Swing Levels — über dieselbe eingeschränkte Tool-Auswahl, die auch der Order-Fokus-Assistent der Chart-Analyse nutzt (`get_order`, `get_order_trace`, `get_order_book`, `get_agent_config`, `get_ec_config`, `get_ec_runs`, `get_agent_decisions`, `get_candles`, `calculate_indicator`, `get_swing_levels`).

Da es sich um ein freischwebendes Fenster statt eines zentrierten Modals handelt, blockiert es die Tabelle im Hintergrund nicht — Sie können weiterklicken oder scrollen (das Fenster bleibt aber an den Trade gebunden, für den es geöffnet wurde; für einen anderen Trade ein neues Fenster öffnen statt zu erwarten, dass es der Auswahl folgt).

**Verwenden, wenn:** Sie eine Frage in natürlicher Sprache zu **genau diesem einen Trade** haben und eine zusammengefasste Antwort statt Rohdaten wollen — z. B. „warum wurde diese Order hier geschlossen?" oder „wenn ich den Entry-Filter anpassen will, wo mache ich das?". Es ist schnelles Q&A zu einem einzelnen Trade, kein Chart-Werkzeug.

**Stattdessen Chart verwenden, wenn:** die Frage eigentlich den **Markt** betrifft, nicht den Order-Datensatz — „zeig mir das gegen EMA und Swing Levels", „was hat der Preis in der Stunde vor dem Entry auf M15 gemacht", „lass mich eine Trendlinie einzeichnen". Der AI-Chat kann Indikatorwerte in Worten beschreiben, aber keinen interaktiven Chart liefern.

### Chart (Liniendiagramm-Symbol, hellblau) — In Chart Analyse öffnen

**Neu.** Wechselt den Action-Tab zur **Chart-Analyse** mit diesem Trade vorgeladen: Die Kerzen werden um das Zeitfenster des Trades verankert, und dieselben Entry/Exit/SL/TP-Preislinien sowie Start/End-Marker, die im eingebetteten Orderbook-Chart zu sehen sind, werden auch dort gezeichnet — jetzt aber innerhalb des vollständigen Chart-Werkzeugs, in dem Sie Indikatoren (EMA, RSI, ATR und weitere) hinzufügen, Swing Levels aktivieren, auf dem Chart zeichnen und mit dem Chart-Analyse-Assistenten sprechen können, der die Trade-Daten bereits im Kontext hat.

**Beispiel:** Sie prüfen in der Tabelle einen geschlossenen Trade mit negativem Ergebnis und wollen ihn gegen EMA-Trend und Swing Levels sehen, bevor Sie beurteilen, ob der Stop sinnvoll platziert war — Klick auf **Chart** in dieser Zeile. Die Chart-Analyse öffnet sich mit dem Zeitfenster des Trades bereits geladen und den Preislinien bereits gezeichnet; anschließend fügen Sie EMA(20) hinzu und aktivieren Swing Levels im Indikator-Panel — etwas, was der eingebettete Orderbook-Chart allein nicht mehr kann.

**Empfehlung:** Greifen Sie zu **AI**, wenn Sie eine Antwort in Textform zu genau einem Trade wollen. Greifen Sie zu **Chart**, wenn Sie den Markt selbst mit echten Chart-Werkzeugen betrachten wollen, oder wenn die Textbeschreibung des AI-Chats („Preis war nahe einem Swing-High") nicht reicht und Sie es sehen wollen. Die beiden Buttons sind keine Doppelung — sie wurden bewusst so gebaut, dass sie nebeneinander existieren.

---

## 5. Schließgründe im Detail

Der Wert in der Close-Spalte kommt direkt aus dem `close_reason`-Enum im Backend, wenn einer gespeichert ist; fehlt er, greift ein Status-Fallback.

### SL_HIT — Stop Loss

Der Preis hat das Stop-Loss-Level erreicht, der Broker hat die Position automatisch mit Verlust geschlossen. Dies ist der normale, geplante Verlust-Exit — das Risikomanagement hat funktioniert. Slippage kann das tatsächliche Ergebnis leicht vom theoretischen Risikobetrag abweichen lassen.

**Analysefrage:** War die Stop-Platzierung angesichts der Marktstruktur beim Entry sinnvoll? Nutzen Sie den **Chart**-Button für eine genauere Prüfung mit Swing Levels.

### TP_HIT — Take Profit

Der Preis hat das Take-Profit-Level erreicht, der Broker hat die Position automatisch mit Gewinn geschlossen. Der normale, geplante Gewinn-Exit.

### TRAILING_STOP — Trailing Stop ausgelöst

Die Position hatte einen Trailing Stop konfiguriert, und der Preis hat sich weit genug zurückbewegt, um ihn auszulösen, bevor das eigentliche Take-Profit-Level erreicht wurde. Typischerweise ein kleinerer Gewinn als ein vollständiger TP-Treffer, aber ein früherer Gewinnschutz.

### AGENT_CLOSED — Von einem Agenten aktiv geschlossen

Ein BA- oder GA-Agent hat die Position direkt geschlossen, außerhalb des SL/TP-Mechanismus — zum Beispiel, weil eine aktualisierte AA-Analyse die Grundlage des Setups mitten im Trade widerlegt hat. Für das „Warum" ist **AI** oder **Trace** auf dieser Zeile der schnellste Weg.

### BROKER_CLOSED — Vom Broker zwangsweise geschlossen

Der Broker hat die Position aus einem Grund geschlossen, der außerhalb der Kontrolle von OpenForexAI liegt — Margin Call, Konto-Einschränkung oder eine broker-seitige Risikomaßnahme. Prüfen Sie die Broker-Plattform direkt; das System zeichnet hier nur auf, was der Broker getan hat.

### SYNC_DETECTED

OpenForexAI hat bei einem regulären Sync-Check festgestellt, dass eine als offen geführte Position beim Broker nicht mehr existiert. Dies ist das Sicherheitsnetz für Schließungen, die passieren, während OpenForexAI nicht aktiv zuschaut (ein `SL_HIT`/`TP_HIT`/`BROKER_CLOSED`-Ereignis beim Broker, das wegen einer Verbindungslücke oder eines Polling-Abstands nicht in Echtzeit erfasst wurde).

**Wann dies auftritt:** eine broker-seitige Schließung zwischen zwei Sync-Zyklen; eine manuelle Schließung direkt auf der Broker-Plattform; oder inkonsistente Broker-API-Antworten über mehrere Checks, die eine Sicherheits-Schließung auslösen.

**Interpretation:** kein Fehler, sondern ein Signal, dass die Position außerhalb des normalen OpenForexAI-Exit-Flows geschlossen wurde. Prüfen Sie die Broker-Plattform für den tatsächlichen Grund.

### REJECTED — Order vor Eröffnung abgelehnt

Die Order wurde nie zu einer Position. Häufige Gründe: unzureichendes Margin, geschlossener Markt (z. B. Wochenend-Gap), ungültige Positionsgröße (unter dem Broker-Minimum), zu weiter Spread zum Zeitpunkt der Übermittlung, oder ein vom Broker ausgesetztes/gesperrtes Instrument. Ein `REJECTED`-Eintrag hat keine bestätigten Von/Bis-Zeitstempel, keine Fill-abgeleiteten Units und kein Ergebnis.

**Analysefrage:** Häufen sich `REJECTED`-Einträge bei einem bestimmten Pair oder zu bestimmten Tageszeiten, braucht der BA-Agent eventuell einen Spread-Filter oder Session-Zeitbeschränkungen.

### Fallback-Werte in der Close-Spalte

Nicht jeder Eintrag hat einen gespeicherten `close_reason`. Fehlt er, zeigt die Spalte stattdessen:

| Angezeigter Wert | Wann |
|---|---|
| `REJECTED` | Status ist `REJECTED`, kein eigener Schließgrund gespeichert |
| `CANCELLED` | Status ist `CANCELLED` — Order wurde gebaut, aber nie an den Broker gesendet |
| `closed` (klein) | Status ist `CLOSED`, aber kein `close_reason` gespeichert — als „geschlossen, Grund nicht erfasst" lesen, nicht als Fehler |
| `running` | Position noch offen — Standardtext für jeden Status, der nicht REJECTED, CANCELLED oder CLOSED ist |

Die kleingeschriebenen Fallback-Texte (`closed`, `running`) sind keine eigenständigen Schließgründe — sie bedeuten nur „kein spezifischer Grund gespeichert".

---

## 6. Trade-Detail-Chart

Wird ein Trade in der Tabelle ausgewählt, lädt der Chart-Bereich unten eine schlanke Vorschau des Preisverlaufs um diesen Trade herum. Der Chart ist absichtlich minimal — nur Kerzen, Preislinien und Marker. **Seit der letzten Änderung gibt es hier keine Indikator-Steuerung mehr** — keine EMA-/RSI-/ATR-Checkboxen, keine Perioden-Eingabefelder, keine Timeframe-Dropdowns pro Indikator. Wenn Sie Indikatoren, Swing Levels oder Zeichenwerkzeuge für diesen Trade brauchen, nutzen Sie den **Chart**-Button (Abschnitt 4), um ihn in der vollständigen Chart-Analyse zu öffnen — suchen Sie nicht nach Indikator-Reglern auf dieser Seite, sie wurden bewusst entfernt, damit das Orderbook auf Trade-Review fokussiert bleibt statt das Chart-Werkzeug zu duplizieren.

### 6.1 Kopfzeile (Info-Boxen)

| Box | Inhalt |
|-----|--------|
| **Pair · Richtung** | z. B. `EUR_USD · BUY`, darunter AA-Entscheidung / Konfidenz / Setup-Typ |
| **Entry / Exit** | Fill-Preis (oder angeforderter Preis, falls nicht gefüllt) und Exit-Preis |
| **SL / TP** | Stop-Loss- und Take-Profit-Preisniveau |
| **Support / Resistance** | Support-/Resistance-Preisniveaus aus dem gespeicherten Analyse-Overlay **zum Zeitpunkt des Trades** — ein statischer, gespeicherter Snapshot, keine Live-Neuberechnung |
| **Indikatoren** | Name-und-Wert-Badges für die Indikatoren, die die AA-Analyse als Kontext für diesen Trade gespeichert hat — ebenfalls statisch und rein lesend, hier nicht konfigurierbar |

Die Support/Resistance- und Indikatoren-Boxen sehen aus wie Steuerelemente, sind es aber nicht — es gibt nichts anzuklicken oder zu konfigurieren. Sie zeigen, was der AA-Agent zum Entscheidungszeitpunkt gespeichert hat. Ein Strich bedeutet meist, dass der Analyse-Datensatz keinen Overlay-Snapshot enthielt — nicht, dass zu diesem Zeitpunkt nichts existierte.

### 6.2 Preislinien im Chart

- **Entry (cyan):** Fill-Preis, falls die Order gefüllt wurde, sonst der ursprünglich angeforderte Preis.
- **Exit (amber):** Exit-Preis, nur gezeichnet, sobald die Order tatsächlich geschlossen ist.
- **SL (rot):** Stop-Loss-Niveau.
- **TP (grün):** Take-Profit-Niveau.
- **Support (türkis) / Resistance (violett):** je eine Linie pro Level aus dem gespeicherten Analyse-Overlay-Snapshot — dieselben Daten wie in der Info-Box oben.

Alle diese Linien sind einfache, über die gesamte Chart-Breite gezeichnete horizontale Preislinien (nicht auf den Zeitraum Entry-bis-Exit begrenzt) — sie markieren Preisniveaus, keine Zeitspanne.

### 6.3 Start-/End-Marker

- **Start-Marker:** ein hervorgehobener Pfeil (aufwärts bei BUY, abwärts bei SELL) an der Kerze nächst dem Öffnungszeitpunkt, positioniert unterhalb der Kerze bei BUY, oberhalb bei SELL.
- **End-Marker:** ein hervorgehobener Kreis an der Kerze nächst dem Schließzeitpunkt, positioniert oberhalb der Kerze bei BUY, unterhalb bei SELL.

Beide Marker nutzen dieselbe Snapping-Logik (`findMarkerTimestamp`), die auf die nächstgelegene geladene Kerze zum tatsächlichen Zeitstempel des Trades einrastet — und, wichtig: **zeigt gar keinen Marker**, wenn der Zeitstempel des Trades deutlich außerhalb des aktuell geladenen Kerzen-Fensters liegt, statt ihn fälschlich an eine Rand-Kerze zu heften. Fehlt ein Start- oder End-Marker nach der Auswahl eines Trades, ist das meist ein Hinweis, dass das geladene Kerzen-Fenster nicht weit genug zurück- oder vorreicht — Timeframe wechseln oder den **Chart**-Button nutzen, der das Kerzen-Fenster gezielt um den Trade verankert.

---

## 7. Chart-Steuerung

Die einzigen Steuerelemente am eingebetteten Chart, in einer schmalen Zeile darüber:

### Show the Analyses — Checkbox

Standardmäßig aktiviert. Blendet jeden AA-Analyse-Zyklus, der für das Pair dieses Trades im relevanten Zeitfenster erfasst wurde, als kleine, **orangefarbene Quadrat-Marker** ein, beschriftet mit `U`, `D` oder `N` und der Konfidenz in Prozent darunter.

- **`U`** — die `primary_bias` der Analyse war long-orientiert (`BIAS_LONG` oder `BIAS_REVERSAL_LONG`)
- **`D`** — die Bias war short-orientiert (`BIAS_SHORT` oder `BIAS_REVERSAL_SHORT`)
- **`N`** — Bias war neutral, oder das Feld ließ sich aus dem Datensatz nicht auslesen

Wichtig: Diese Beschriftung zeigt **ausschließlich die Richtungs-Bias** — nicht, ob die Analyse den Moment als guten Entry-Zeitpunkt eingestuft hat (`order_start_signal`). Alle Marker haben dieselbe Farbe und Form; nur Buchstabe und Konfidenzwert unterscheiden sich.

Ein Klick auf einen Marker öffnet das AA-Recommendation-Popup für genau diesen Analyse-Zyklus (Abschnitt 8).

**Wann aktivieren:** wenn Sie den analytischen Kontext um einen Trade sehen wollen, nicht nur den Trade selbst. Beispiel: Ging ein Trade in den Verlust — gab es nachfolgende `D`/`N`-Zyklen, die zeigen, dass die Bias sich gegen die Trade-Richtung gedreht hat, während die Position noch offen war?

### Timeframe-Buttons

**Verfügbar:** M5, M15, M30, H1 (kein H4 oder D1 — diese gibt es nur in der Chart-Analyse).

Wechselt den Chart auf den gewählten Timeframe und lädt bis zu 2000 Kerzen dafür neu. Preislinien und Start-/End-Marker werden automatisch neu positioniert.

**Typische Nutzung:** H1 für den übergeordneten Kontext, M15 für das Entry-Timing, M5 für die exakten Entry-/Exit-Kerzen. Verschwindet ein Start- oder End-Marker beim Wechsel, siehe den Hinweis am Ende von Abschnitt 6 zu Markern außerhalb des geladenen Fensters.

### Kerzen-Bereich-Shortcuts

Der Chart selbst (nicht spezifisch für das Orderbook) bietet Schnellzugriffe auf die letzten 50 / 100 / 200 / 400 Kerzen, standardmäßig 100. Diese ändern nur, wie viele der geladenen Kerzen gerade sichtbar sind — sie laden keine neuen Daten nach, und ein Timeframe- oder Trade-Wechsel setzt die Ansicht auf den Standardwert zurück.

---

## 8. AA-Analyse- und Recommendation-Popup

### 8.1 AA-Analyse-Popup (Open-Button)

**Inhalt:**
- Der vollständige gespeicherte Analysetext des AA-Agents zu diesem Trade.
- Ein **Copy-Button**, um den Text in die Zwischenablage zu kopieren.
- Ein **Close-Button**, um das Popup zu schließen.

Dies ist die definitive Antwort auf „was hat das System gedacht, als es entschieden hat, einzusteigen?". Bei einem Verlust-Trade zeigt dieses Popup, ob die Analyse angesichts der damals verfügbaren Informationen vernünftig war (und der Verlust einfach Pech oder ungünstige Ausführung war), oder ob die Analyse selbst fehlerhaft war.

### 8.2 AA-Recommendation-Popup (Klick auf einen Chart-Marker)

Wird durch Klick auf einen `U`/`D`/`N`-Marker geöffnet (erfordert aktivierte „Show the Analyses"-Checkbox).

Ein 4-Spalten-Grid zeigt:
- **Decision** — das Entscheidungsfeld der AA für diesen Zyklus
- **Confidence** — der Konfidenzwert aus dem LLM-Output
- **Order Start** — der `order_start_signal`-Wert (Einstiegsbereitschaft)
- **Entry Quality** — die gespeicherte Bewertung der Einstiegsqualität

Darunter:
- **Decision JSON** — die vollständige Entscheidungsausgabe (bzw. der gespeicherte Analysetext, falls vorhanden), mit Copy-Button.
- **Decision Snapshot** — der vollständige Markt-Snapshot, den die AA zum Zeitpunkt dieser Analyse erhalten hat, mit Schema-Version-Tag (falls gespeichert) und eigenem Copy-Button. Dieser Abschnitt erscheint nur, wenn tatsächlich ein Snapshot mit dem Datensatz gespeichert wurde — ältere Einträge oder Konfigurationen ohne Snapshot-Speicherung zeigen hier schlicht nichts an.

**Warum der Snapshot hier wertvoll ist:** Bei der Nachanalyse eines historischen Trades zeigt der Snapshot exakt, welche Daten der Agent damals hatte — nicht was Sie heute sehen, sondern was zu jener Kerze zu jenem Zeitpunkt existierte. Dies ist der zuverlässigste Weg, eine KI-Handelsentscheidung nachträglich zu prüfen.

---

## 9. Print und Knowledgebase-Export

Beide Aktionen sind erst aktiv, wenn ein Trade ausgewählt ist, und beide bauen auf **denselben zugrundeliegenden Report-Inhalt** auf — nur das Ziel unterscheidet sich.

### 9.1 Print-Button

Ein Klick auf Print öffnet sofort ein neues Browser-Fenster und schreibt einen eigenständigen, druckoptimierten HTML-Report — es gibt **keinen Auswahl-Dialog** mit Checkboxen (diesen gibt es nur bei der Print-Funktion der Chart-Analyse, nicht hier). Der Report enthält immer:

- **Timing** — Von/Bis-Zeitstempel und den Close-Status-Text
- **Execution** — Entry-Preis, Exit-Preis, SL/TP, Units
- **Result** — Stake-Schätzung, P&L, AA-Entscheidung, Konfidenz
- **AA Context** — die gespeicherten Indikator-Badges und Support-/Resistance-Level aus dem Analyse-Overlay
- **Chart** — ein Screenshot des Charts exakt so, wie er aktuell aussieht (welcher Timeframe und Show-the-Analyses-Zustand zuletzt eingestellt war)
- **AA Analysis** — der vollständige Analysetext auf einer eigenen Seite (mit erzwungenem Seitenumbruch davor)

Das Fenster löst nach dem Laden automatisch den nativen Druckdialog des Browsers aus. Von dort aus können Sie physisch drucken, als PDF speichern oder Ränder/Ausrichtung/Skalierung über die Browser-Druckeinstellungen anpassen.

**Tipp:** Stellen Sie Timeframe und „Show the Analyses" so ein, wie sie im Ausdruck erscheinen sollen, **bevor** Sie auf Print klicken — das erfasste Chart-Bild zeigt genau das, was aktuell gerendert ist, keine feste Standardansicht.

### 9.2 → KB-Button

Baut denselben Inhalt als Markdown-Dokument statt als HTML/Print-Report und speichert ihn über `kbImport` in der Knowledgebase, in einem automatisch verwalteten „Import"-Ordner mit dem Titel `Orderbook_<Zeitstempel>`. Das Markdown enthält dasselbe Chart-Bild (eingebettet), Result-/Timing-/Execution-Tabellen, AA Context und — falls der gespeicherte `market_context_snapshot` des Trades einen `analyst_recommendation`-Block enthält — eine strukturierte Langfassung (Decision, Signal, Quality, Setup-Typ, Aggressiveness, Invalidation-Level, First Target, Conflict Flags, plus Fließtext-Abschnitte zu Summary, Entry-Reason, Trend-/Momentum-/Volatility-/S-R-/M5-Price-Action-Einschätzung und Entry-Quality-Begründung) statt des rohen Analysetexts.

**Print verwenden, wenn** Sie etwas außerhalb des Systems weitergeben wollen (PDF für eine Broker-Klärung, physisches Trading-Journal). **→ KB verwenden, wenn** die Zusammenfassung dauerhaft in der OpenForexAI-Knowledgebase für spätere Recherche oder für andere Assistenten/Agenten durchsuchbar sein soll.

---

## 10. Typische Arbeitsabläufe

### 10.1 Tägliche P&L-Überprüfung

1. Filter auf **geschlossen** setzen.
2. **Max Orders** über den Standardwert 7 hinaus erhöhen, um den Tag abzudecken (z. B. 20–50).
3. **Refresh** klicken (löst auch einen Broker-Sync aus — Spinner abwarten).
4. Ergebnis-Spalte durchsehen: Wo Gewinn, wo Verlust?
5. Bei jedem geschlossenen Trade die Zeile anklicken für den eingebetteten Chart, und „Show the Analyses" aktivieren für den Analyse-Kontext.
6. Bei einem Verlust-Trade: **Open** klicken, AA-Analyse lesen — war sie fundiert, oder war der Markt trotz korrekter Einschätzung ungünstig?
7. Close-Spalte prüfen: Waren alle Schließungen `SL_HIT` oder `TP_HIT` (geplant)? `SYNC_DETECTED`- oder `BROKER_CLOSED`-Einträge verdienen einen genaueren Blick über **Trace** oder **AI**.

### 10.2 Verlust-Trade Schritt für Schritt untersuchen

**Ziel:** verstehen, ob ein Verlust-Trade ein Systemfehler war oder ein regulärer Verlust innerhalb einer gültigen Strategie.

1. Verlust-Trade in der Tabelle finden (Filter **geschlossen**, rote Ergebnisse).
2. Zeile anklicken für einen ersten Blick im eingebetteten Chart, dann **Chart** klicken, um denselben Trade in der vollständigen Chart-Analyse zu öffnen — für diesen Workflow brauchen Sie Indikatoren und Swing Levels, die der eingebettete Chart nicht mehr bietet.
3. In der Chart-Analyse zunächst H1: War die Richtung für den übergeordneten Kontext korrekt? EMA hinzufügen zur Prüfung.
4. Wechsel zu M15: War der Entry an einer sinnvollen Stelle relativ zur Struktur?
5. SL-Linie prüfen: Lag der Stop unter dem nächsten Swing Low (bei Long), oder zu eng, innerhalb des normalen Kursrauschens? Swing Levels aktivieren, um dies objektiv statt nach Augenmaß zu beurteilen.
6. Zurück im Orderbook: **Open** klicken, AA-Analyse lesen — hat der Agent das Setup korrekt erkannt?
7. „Show the Analyses" am eingebetteten Chart aktivieren und nahegelegene `U`/`D`/`N`-Marker anklicken — war die Bias konsistent, oder hat sie sich gedreht, während der Trade noch offen war?
8. Falls aus dem Datensatz allein nicht klar: **AI** klicken und direkt fragen — z. B. „warum hat sich die AA-Bias 20 Minuten nach diesem Entry gedreht?".
9. War die Analyse fundiert und der Stop strukturell sinnvoll platziert, hat der Preis ihn aber trotzdem erreicht: ein regulärer Verlust-Trade, keine Aktion nötig. War die Analyse fehlerhaft oder der Stop schlecht platziert: ein Strategie-/Konfigurationsproblem.

### 10.3 SYNC_DETECTED oder BROKER_CLOSED untersuchen

1. Trade-Zeile anklicken, Chart laden. Bis-Zeitstempel beachten — bei `SYNC_DETECTED` ist dies der Zeitpunkt der *Erkennung*, nicht notwendigerweise der tatsächliche Schließzeitpunkt.
2. **Trace** klicken — zeigt die umgebende Event-Kette; ging der Schließung ein Sync-Zyklus-Event unmittelbar voraus?
3. **AI** klicken und fragen, z. B. „was sagt der Order-Datensatz über die Ursache dieser Schließung?" — der Assistent kann Trace und Agent-Konfiguration in einem Schritt abrufen, statt dass Sie es manuell zusammensetzen.
4. Broker-Plattform über die Id des Trades direkt gegenprüfen — was zeigt der Broker selbst als Schließgrund?
5. Häufiges Ergebnis: Der Broker hat den Trade geschlossen (Margin Call, eigenes Risikomanagement oder eine geplante Wochenend-/Rollover-Schließung), und OpenForexAI hat dies erst beim nächsten Sync erkannt — der Eintrag ist eine korrekte Aufzeichnung, kein Fehler.

### 10.4 Abgelehnte Trades analysieren

**Ziel:** Muster bei abgelehnten Orders erkennen, um die BA-Agent-Konfiguration zu verbessern.

1. Filter auf **abgelehnt**, **Refresh** klicken.
2. Pair-Spalte prüfen — häufen sich Ablehnungen bei einem bestimmten Pair?
3. Von-Zeitstempel prüfen — Häufung zu bestimmten Zeiten (z. B. Markteröffnung, liquiditätsarme Phasen)?
4. Units und Ergebnis sind beide leer — bestätigt, dass nie eine Position existierte.
5. Einen abgelehnten Trade anklicken, dann **Chart**, um Spread-/Preisbedingungen zum Ablehnungszeitpunkt mit vollen Chart-Werkzeugen zu prüfen.
6. Bei zeitlicher Häufung: Spread-Filter oder Session-Zeitbeschränkungen für den BA-Agenten erwägen.

---

## 11. Szenarien und Beispiele

### Szenario A: Gewinner-Trade — Setup validieren

**Trade:** GBPUSD SELL, 4h15m Dauer, positives Ergebnis, Close: TP_HIT.

1. **Chart** klicken, in der Chart-Analyse auf H1 — klarer Abwärtstrend bestätigt.
2. Wechsel zu M15 — der Start-Marker zeigt einen Short-Entry nach einem Pullback zu einem Resistance-Level. Strukturell sauber.
3. Die SL-Preislinie liegt über dem Swing High, das die Resistance definiert hat; die TP-Linie liegt am nächsten Support-Level.
4. Zurück im Orderbook: „Show the Analyses" aktivieren — die `D`-Marker vor dem Entry waren konsistent mit steigenden Konfidenzwerten.
5. Nächstgelegenen `D`-Marker anklicken — hohe Konfidenz, günstige Entry Quality.
6. Fazit: saubere Struktur, korrekte Ausführung, verdienter Gewinn. Keine Aktion nötig.

### Szenario B: Verlust-Trade — vorzeitiger Stop Loss

**Trade:** EURUSD BUY, 0h22m Dauer, negatives Ergebnis, Close: SL_HIT.

1. Chart-Button → H1: Preis insgesamt bullisch, aktuell aber in einer Retracement-Phase.
2. M5: der Start-Marker liegt während der Retracement; der Preis fiel weiter, bevor der SL erreicht wurde.
3. Die SL-Linie liegt nahe am Entry — einen ATR-Indikator in der Chart-Analyse hinzufügen, um zu prüfen, ob der Stop innerhalb des normalen Rauschens lag.
4. Zurück im Orderbook: **Open** klicken — die AA-Analyse beschrieb den Markt als bullisch mit einer Retracement-Kaufgelegenheit. Richtung korrekt.
5. Fazit: die Richtungseinschätzung war richtig, der Stop wahrscheinlich zu eng relativ zur Volatilität. Ein breiterer ATR-basierter SL-Multiplikator in der BA-Konfiguration wäre zu erwägen.

### Szenario C: SYNC_DETECTED-Trade-Audit

**Trade:** USDCAD BUY, 1h55m Dauer, negatives Ergebnis, Close: SYNC_DETECTED.

1. Der Bis-Zeitstempel zeigt, dass die Schließung um 17:33 UTC an einem Freitag *erkannt* wurde — nicht notwendigerweise, wann sie tatsächlich passierte.
2. **Trace** klicken — die umgebenden Events zeigen einen Sync-Zyklus um 17:33, der die Position beim Broker bereits geschlossen vorfand.
3. Die Broker-Plattform bestätigt die tatsächliche Schließung um 17:00 UTC, eine Wochenend-Margin-Anpassung des Brokers.
4. Der `SYNC_DETECTED`-Eintrag ist korrekt — OpenForexAI hat aufgezeichnet, was der Broker getan hat, nur 33 Minuten später bemerkt.
5. Maßnahme: erwägen, den BA-Agenten so zu konfigurieren, dass ab 16:30 UTC freitags keine neuen Positionen mehr eröffnet werden, um Wochenend-Schließungen des Brokers zu vermeiden.

### Szenario D: Häufung von Ablehnungen bei Markteröffnung

**Einträge:** fünf aufeinanderfolgende `REJECTED`-Einträge für EURUSD BUY zwischen 08:00–08:05 UTC an mehreren Tagen.

1. Filter auf **abgelehnt** — die Häufung liegt genau bei der Frankfurt-Session-Eröffnung.
2. **Chart** bei einem der Einträge klicken, um das Spread-Verhalten zu diesem Zeitpunkt auf einem niedrigen Timeframe zu prüfen — Spreads weiten sich oft direkt bei Eröffnung stark.
3. Es ist aktuell kein Spread-Filter im BA-Agenten konfiguriert, daher werden Orders direkt in den weiten Spread hinein übermittelt und abgelehnt.
4. Maßnahme: einen Max-Spread-Filter in der BA-Agent-Konfiguration hinzufügen (z. B. Entry ablehnen, wenn Spread > 2,0 Pips). Nach Konfigurationsänderung und Neustart sollten die Ablehnungen bei Eröffnung aufhören.

---

## 12. Schnellreferenz

### Filter-Buttons

| Filter | Zeigt |
|---|---|
| alle | Alle Trades unabhängig vom Status (einziger Weg zu `CANCELLED`-Einträgen) |
| offen | PENDING, OPEN und PARTIALLY_FILLED zusammen |
| geschlossen | Abgeschlossene Trades — jeder Schließgrund |
| abgelehnt | Nie eröffnete Orders (Broker-/Validierungs-Ablehnung) |

### Aktions-Buttons pro Zeile

| Button | Symbol | Öffnet | Am besten für |
|---|---|---|---|
| Open | Dokument | AA-Analyse-Textpopup | Den gespeicherten Analysetext wörtlich lesen |
| Trace | Verzweigung | Event-Trace-Ansicht | Die kausale Event-Kette verstehen |
| AI | Roboter | Ask-AI-Untersuchungs-Chat | Eine Frage in natürlicher Sprache zu genau diesem Trade |
| Chart | Liniendiagramm | Chart-Analyse, auf den Trade fokussiert | Volle Chart-Werkzeuge (Indikatoren, Swing Levels, Zeichnen) für diesen Trade |

### Schließgründe

| Schließgrund | Bedeutung | Ergebnis-Vorzeichen |
|---|---|---|
| SL_HIT | Stop Loss erreicht — geplanter Verlust | Negativ |
| TP_HIT | Take Profit erreicht — geplanter Gewinn | Positiv |
| TRAILING_STOP | Trailing Stop ausgelöst | Positiv (meist kleiner als TP) |
| AGENT_CLOSED | Ein Agent hat direkt geschlossen | Beides möglich |
| BROKER_CLOSED | Broker hat zwangsweise geschlossen | Beides möglich |
| SYNC_DETECTED | Broker-seitige Schließung bei Sync erkannt | Beides möglich |
| REJECTED | Nie eröffnet — Broker-/Validierungs-Ablehnung | Kein Ergebnis |
| *(Fallback)* CANCELLED | Nie übermittelt — Storno vor Ausführung | Kein Ergebnis |
| *(Fallback)* closed | Status CLOSED, aber kein Grund gespeichert | Beides möglich |
| *(Fallback)* running | Noch offen | — |

### Chart-Marker und -Linien

| Marker/Linie | Farbe | Bedeutung |
|---|---|---|
| Start-Marker | Cyan, hervorgehobener Pfeil | Eröffnungskerze |
| End-Marker | Amber, hervorgehobener Kreis | Schließungskerze |
| Entry-Linie | Cyan horizontal | Fill- (oder angeforderter) Preis |
| Exit-Linie | Amber horizontal | Exit-Preis |
| SL-Linie | Rot horizontal | Stop-Loss-Niveau |
| TP-Linie | Grün horizontal | Take-Profit-Niveau |
| Support-Linie | Türkis horizontal | S/R-Level aus dem gespeicherten Analyse-Overlay |
| Resistance-Linie | Violett horizontal | S/R-Level aus dem gespeicherten Analyse-Overlay |
| U-/D-/N-Marker | Orange, Quadrat | AA-Bias: long- / short-orientiert / neutral, mit Konfidenz in % |

### Spalten-Referenz

| Spalte | Inhalt | Gelb = |
|---|---|---|
| Pair | Instrument, Richtung, Status | — |
| Von | Entry-Zeitstempel | Nur lokal, Broker nicht bestätigt |
| Bis | Exit-Zeitstempel | Nur lokal, Broker nicht bestätigt |
| HH:MM | Trade-Dauer | — |
| Id | Broker-Order-ID | — |
| Units | Positionsgröße in Einheiten der Basiswährung | — |
| Stake | Nominaler Dollar-Positionswert (Preis × Units) — **keine** % vom Eigenkapital | — |
| Ergebnis | P&L in Kontowährung | — |
| Close | Schließgrund (oder Status-Fallback) | — |
| Analysis | Open-/Trace-/AI-/Chart-Buttons | — |

---

## 13. Häufige Fragen

**F: Warum zeigt die Ergebnis-Spalte bei einer offenen Position nichts an?**

A: Für offene Positionen wird in der Tabelle kein Live-P&L berechnet — die Spalte bleibt leer, bis der Trade schließt. Für den aktuellen unrealisierten Gewinn/Verlust die Broker-Plattform oder den GA-Monitor-Agenten prüfen.

**F: Was bedeutet das Ausrufezeichen neben dem Pair?**

A: Es zeigt, dass der Eintrag noch keine Broker-Bestätigung erhalten hat. Die Zeitstempel (Von/Bis) können daher noch lokal und vorläufig sein (gelb angezeigt). Löst sich nach dem nächsten Broker-Sync auf, üblicherweise innerhalb von Sekunden bis wenigen Minuten.

**F: Die Close-Spalte zeigt SYNC_DETECTED. Ist das ein Fehler?**

A: Nein. Es ist ein informativer Status: OpenForexAI hat die Position nicht aktiv geschlossen, sondern beim nächsten Sync-Check festgestellt, dass sie beim Broker nicht mehr existiert. Broker-Plattform prüfen, um den tatsächlichen Grund (SL/TP-Treffer, manuelles Schließen, Margin Call) zu erfahren.

**F: Kann ich im Orderbook manuell Trades schließen?**

A: Nein. Das Orderbook ist eine reine Inspektions- und Analyse-Seite, keine Trading-Seite. Zum manuellen Schließen die Broker-Plattform direkt nutzen — OpenForexAI erkennt die Schließung beim nächsten Sync-Check automatisch und trägt sie als `BROKER_CLOSED` oder `SYNC_DETECTED` nach.

**F: Warum sind manche Einträge gelb dargestellt?**

A: Gelbe Von-/Bis-Felder zeigen an, dass der Zeitstempel noch lokal ist und noch nicht vom Broker bestätigt wurde. Ein vorübergehender Zustand, der sich nach dem Broker-Sync auflöst.

**F: Ich sehe viele REJECTED-Einträge. Was läuft falsch?**

A: Mögliche Ursachen: unzureichendes Margin, geschlossener Markt, ungültige Positionsgröße unter dem Broker-Minimum, zu weiter Spread bei Übermittlung, oder ein ausgesetztes Instrument. Häufen sich Ablehnungen bei einem bestimmten Pair oder zu bestimmten Zeiten, im BA-Agenten einen Spread-Filter oder Session-Zeitbeschränkungen erwägen. Details zum konkreten Fall über den **AI**-Button auf der jeweiligen Zeile erfragen.

**F: Wo finde ich EMA/RSI/ATR für einen Trade im Orderbook?**

A: Nirgends mehr direkt im Orderbook — diese Steuerelemente wurden aus dem eingebetteten Chart entfernt. Für Indikatoren, Swing Levels und Zeichenwerkzeuge auf einem bestimmten Trade den **Chart**-Button in der Analysis-Spalte dieser Zeile verwenden, um den Trade in der vollständigen Chart-Analyse zu öffnen.

**F: Was ist der Unterschied zwischen dem AI-Button und dem Chart-Button?**

A: **AI** öffnet einen Chat, der Fragen in natürlicher Sprache zu genau diesem Trade beantwortet und dafür bei Bedarf selbst weitere Daten abruft (Trace, Agent-/EC-Konfiguration, Kerzen). **Chart** öffnet denselben Trade in der vollständigen Chart-Analyse mit echten Chart-Werkzeugen (Indikatoren, Swing Levels, Zeichnen). Beide ergänzen sich — nutzen Sie AI für eine schnelle Text-Antwort, Chart, wenn Sie selbst am Chart arbeiten wollen.
