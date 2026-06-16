[Zurück zu Action](ui.action.de.md)

# Orderbook — Handbuch

Das **Orderbook** ist die operative Inspektionsseite für alle Trade-Einträge. Es zeigt eine vollständige Tabelle aller Orders und — bei Auswahl eines Eintrags — einen verknüpften Chart, der den exakten Marktkontext der Trade-Position darstellt. Das Orderbook ist das primäre Werkzeug zur Nachanalyse von Trades, zur Überprüfung offener Positionen und zur Fehlersuche bei der Trade-Ausführung.

---

## 1. Filterleiste

Die Filterleiste befindet sich oben auf der Orderbook-Seite und steuert, welche Einträge in der Tabelle geladen und angezeigt werden.

### 1.1 Status-Filter

Die Status-Filter-Buttons erlauben die Einschränkung der angezeigten Trades nach ihrem aktuellen Status:

| Filter | Bedeutung |
|--------|-----------|
| **alle** | Zeigt alle Trade-Einträge unabhängig vom Status. Standard nach dem Öffnen der Seite. |
| **offen** | Zeigt nur Positionen, die derzeit aktiv beim Broker offen sind. |
| **geschlossen** | Zeigt nur bereits abgeschlossene Positionen (durch SL, TP, manuelle Schließung oder Sync). |
| **abgelehnt** | Zeigt Einträge, bei denen die Trade-Ausführung abgelehnt wurde (z. B. durch Risikoprüfung oder Broker-Ablehnung). |
| **storniert** | Zeigt Einträge, die storniert wurden, bevor sie ausgeführt wurden. |

**Empfehlung:** Verwenden Sie den Filter **offen** regelmäßig, um einen schnellen Überblick über alle aktiven Positionen zu erhalten. Den Filter **abgelehnt** ist besonders nützlich bei der Fehlersuche, wenn erwartet wurde, dass Trades ausgeführt werden, aber keine offenen Positionen sichtbar sind.

### 1.2 Max Orders

Das **Max Orders**-Feld begrenzt die Anzahl der angezeigten Einträge in der Tabelle. Dies ist bei großen Historien mit hunderten von Trades nützlich, um die Ladezeit zu reduzieren.

- **Standardwert:** 50 (je nach Konfiguration)
- **Eingabe:** Ganzzahl ≥ 1
- **Anwendung:** Nach Verlassen des Feldes oder Drücken von Enter wird die Tabelle neu geladen.

Für die tägliche Kontrolle reichen meist 20–30 Einträge. Für eine vollständige historische Analyse kann der Wert auf 500 oder mehr erhöht werden.

### 1.3 Refresh-Button

Der **Refresh**-Button lädt die Trade-Tabelle manuell neu. Das Orderbook hat kein automatisches Polling — Sie bestimmen, wann neue Daten geladen werden.

Ein Spinner-Icon erscheint während des Ladevorgangs. Der Button ist während des Ladens deaktiviert.

**Wann Refresh verwenden:**
- Nach einem vermuteten neuen Trade (z. B. wenn im Monitor ein `order_placed`-Event sichtbar war).
- Wenn Sie die aktuellsten Informationen zu offenen Positionen benötigen.
- Nach einem Broker-Sync, um den aktualisierten Status zu sehen.

### 1.4 Print-Button

Der **Print**-Button öffnet den Print-Dialog für den aktuell in der Tabelle ausgewählten Eintrag. Er ist nur aktiv, wenn ein Trade ausgewählt ist.

Der Print-Dialog bietet Optionen, was in den Ausdruck einbezogen werden soll:
- Chart (aktuelle Chart-Darstellung des Trades)
- Kerzen-Daten (OHLCV der relevanten Kerzen)
- Analyse-Daten (AA-Analyse-Snapshot, wenn vorhanden)

Nach der Auswahl öffnet sich der Browser-Druckdialog mit einer druckoptimierten HTML-Ansicht.

---

## 2. Trade-Tabelle

Die **Trade-Tabelle** ist das Herzstück des Orderbuchs. Jede Zeile repräsentiert einen Trade-Eintrag. Ein Klick auf eine Zeile wählt den Eintrag aus und lädt den zugehörigen Chart im unteren Bereich.

### 2.1 Spalten der Tabelle

#### Pair

Zeigt das **Währungspaar** (z. B. `EUR_USD`), die **Handelsrichtung** (`BUY` oder `SELL`) und den **Status** des Eintrags (z. B. `open`, `closed`).

Wenn der Eintrag noch nicht vom Broker bestätigt wurde (z. B. Order kurz nach Ausführung, noch kein Broker-Callback empfangen), erscheint ein **Warnsymbol** (Ausrufezeichen) neben dem Pair. Dies ist ein normaler kurzfristiger Zustand und kein Fehler.

#### Von (From)

Der **Startzeitpunkt** der Trade-Position — wann die Position eröffnet wurde.

- **Grau/weiß:** Zeitstempel wurde vom Broker bestätigt.
- **Gelb:** Zeitstempel ist nur lokal (noch kein Broker-Timestamp empfangen). Dieser Zustand ist kurzfristig und löst sich nach dem nächsten Sync-Check auf.

Der Zeitstempel wird in der lokalen Zeitzone des Systems angezeigt.

#### Bis (To)

Der **Endzeitpunkt** der Position — wann die Position geschlossen wurde. Bei offenen Positionen ist dieses Feld leer oder zeigt einen Platzhalter.

Wie bei **Von** wird Gelb angezeigt, wenn der Zeitstempel nur lokal ist.

#### Dauer (HH:MM)

Die **Dauer der Position** in Stunden und Minuten, berechnet aus dem Unterschied zwischen **Von** und **Bis**. Bei offenen Positionen wird die aktuelle Laufzeit in Echtzeit angezeigt (bzw. bei manuellem Refresh aktualisiert).

Beispiele:
- `00:23` — Position lief 23 Minuten
- `02:45` — Position lief 2 Stunden und 45 Minuten
- `14:30` — Position lief 14 Stunden und 30 Minuten (z. B. über Nacht)

#### ID

Die **Broker-Order-ID** — die eindeutige Kennung, unter der diese Position beim Broker registriert ist. Diese ID kann verwendet werden, um die Position direkt in der Broker-Plattform nachzuschlagen.

- Zeigt `-`, wenn noch keine Broker-ID zugewiesen wurde (Position wurde noch nicht bestätigt).
- Die ID ist unveränderlich und bleibt auch nach dem Schließen der Position erhalten.

#### Einheiten (Units)

Die **Positionsgröße** in Währungseinheiten (Lots oder Units je nach Broker-Konvention). Formatiert mit Tausenderpunkt für bessere Lesbarkeit.

Beispiele:
- `1.000` — 1.000 Units (Standard Micro-Lot in manchen Broker-Systemen)
- `10.000` — 10.000 Units
- `100.000` — 100.000 Units (Standard Lot)

Die Positionsgröße wird vom BA-Agent basierend auf dem konfigurierten Risiko-Prozentsatz und dem Kontoguthaben berechnet.

#### Einsatz % (Stake)

Der **geschätzte prozentuale Einsatz** dieser Position am Gesamtkontoguthaben. Dieser Wert gibt an, wie viel Prozent des Kontos durch diese Position riskiert werden (basierend auf dem Stop-Loss-Abstand zum Entry).

Angezeigt mit 2 Dezimalstellen, z. B.:
- `1.00` — 1% des Kontoguthabens riskiert
- `2.50` — 2.5% des Kontoguthabens riskiert

Der Einsatz-Prozentsatz wird zum Zeitpunkt der Trade-Eröffnung berechnet und ändert sich danach nicht mehr (auch wenn das Konto-Guthaben schwankt).

#### Ergebnis (P&L — Result)

Das **Gewinn- oder Verlustkonto** dieser Position in der Kontowährung.

- **Grün** (≥ 0): Position im Gewinn oder break-even
- **Rot** (< 0): Position im Verlust

Bei **offenen Positionen** zeigt das Ergebnis den aktuellen unrealisierten Gewinn/Verlust zum Zeitpunkt des letzten Refresh.

Bei **geschlossenen Positionen** zeigt das Ergebnis den endgültigen realisierten Gewinn/Verlust.

Das P&L wird vom Broker übermittelt und beinhaltet Spread und ggf. Swaps.

#### Schließgrund (Close)

Der **Schließgrund** erklärt, warum und wie eine Position geschlossen wurde. Für offene Positionen ist dieses Feld leer.

### 2.2 Schließgründe im Detail

Die Schließgründe sind codierte Werte, die den Auslöser für das Schließen der Position beschreiben:

#### SL — Stop Loss

```
Schließgrund: SL
```

Die Position wurde durch den **Stop-Loss** geschlossen. Der Preis hat das Stop-Loss-Level erreicht und der Broker hat die Position automatisch mit einem Verlust geschlossen.

- Dies ist der normale Verlust-Exit-Mechanismus.
- Stop-Loss-Orders liegen beim Broker und werden auch ohne aktive OpenForexAI-Verbindung ausgeführt.
- OpenForexAI erkennt den SL-Abschluss beim nächsten Sync-Check und aktualisiert den Status in der Datenbank.

#### TP — Take Profit

```
Schließgrund: TP
```

Die Position wurde durch den **Take-Profit** geschlossen. Der Preis hat das Take-Profit-Level erreicht und der Broker hat die Position automatisch mit einem Gewinn geschlossen.

- Dies ist der normale Gewinn-Exit-Mechanismus.
- Wie SL-Orders liegen TP-Orders beim Broker und werden unabhängig von OpenForexAI ausgeführt.

#### SYNC_DETECTED

```
Schließgrund: SYNC_DETECTED
```

OpenForexAI hat beim Sync-Check festgestellt, dass eine Position, die lokal als offen gespeichert war, beim Broker nicht mehr existiert. Dies tritt auf, wenn:

- Die Position durch SL oder TP geschlossen wurde, während OpenForexAI keine Verbindung hatte.
- Die Position manuell über die Broker-Plattform (außerhalb von OpenForexAI) geschlossen wurde.
- Der Broker die Position aus einem anderen Grund geschlossen hat (z. B. Margin-Call, Wochenend-Schließung).

OpenForexAI markiert die Position dann mit `SYNC_DETECTED` und versucht, das tatsächliche P&L und den genauen Schließzeitpunkt vom Broker abzurufen.

**Interpretation:** `SYNC_DETECTED` ist kein Fehler, sondern ein Signal, dass die Position außerhalb des normalen OpenForexAI-Exit-Flows geschlossen wurde. Prüfen Sie die Broker-Plattform für Details zum tatsächlichen Schließgrund.

#### MANUELL

```
Schließgrund: MANUELL
```

Die Position wurde manuell über OpenForexAI oder direkt über die Broker-Plattform geschlossen (z. B. über einen manuellen Close-Befehl).

#### ABGELEHNT

```
Schließgrund: ABGELEHNT
```

Der Trade wurde abgelehnt, bevor er erfolgreich ausgeführt werden konnte. Mögliche Gründe:

- **Broker-Ablehnung:** Unzureichendes Margin, ungültige Parameter, Broker-seitige Einschränkungen.
- **Risikoprüfung:** OpenForexAI hat den Trade intern abgelehnt (z. B. maximales tägliches Risiko überschritten, Duplikat-Signal erkannt).
- **Konfigurationsfehler:** Ungültige SL/TP-Werte, falsche Positionsgröße.

Details zum Ablehnungsgrund sind in der Analysis-Spalte oder im Monitor einsehbar.

---

## 3. Analyse-Spalte und AA-Analyse-Popup

### 3.1 Analysis-Button

Die letzte Spalte der Tabelle enthält für jeden Trade-Eintrag einen **„Open"**-Button in der Analysis-Spalte (sofern eine AA-Analyse zu diesem Trade vorhanden ist).

### 3.2 AA-Analyse-Popup

Ein Klick auf **„Open"** öffnet ein Popup-Fenster, das den vollständigen gespeicherten Analysetext des AA-Agents für diesen Trade-Eintrag zeigt.

Das Popup enthält:

- **Vollständiger Analysetext** — die gesamte Ausgabe des AA-Agents zum Zeitpunkt der Entscheidung
- **Copy-Button** — kopiert den Analysetext in die Zwischenablage
- **Close-Button** — schließt das Popup

Dies ist nützlich, um zu verstehen, welche Marktbedingungen und welche LLM-Begründung zur Entscheidung für diesen Trade geführt haben.

---

## 4. Resize-Trennlinie

Die **Trennlinie** zwischen der Trade-Tabelle und dem Chart-Bereich kann per Maus nach oben oder unten verschoben werden. Dies erlaubt es, mehr Platz für die Tabelle oder für den Chart zu reservieren.

- Tabelle kann auf 28–72 % der Gesamtseitenhöhe eingestellt werden.
- Der Rest wird vom Chart eingenommen.

---

## 5. Trade-Detail-Chart

Wenn ein Trade-Eintrag in der Tabelle ausgewählt wird, lädt der **Trade-Detail-Chart** im unteren Bereich der Seite und zeigt den Kursverlauf zum Zeitpunkt des Trades mit allen relevanten Preisniveaus und Analyse-Markern.

### 5.1 Chart-Kopfzeile (Info-Boxes)

Die Kopfzeile des Charts zeigt die wichtigsten Kennzahlen der ausgewählten Position in kompakten Info-Boxen:

| Box | Inhalt |
|-----|--------|
| **Pair · Richtung** | Währungspaar (z. B. `EUR_USD`) und Trade-Richtung (`BUY` / `SELL`) |
| **Entry** | Tatsächlicher Einstiegspreis der Position |
| **Exit** | Tatsächlicher Ausstiegspreis (bei offener Position: aktueller Kurs) |
| **SL** | Stop-Loss-Level (absoluter Preis) |
| **TP** | Take-Profit-Level (absoluter Preis) |
| **Support** | Identifizierte Support-Niveaus aus der AA-Analyse |
| **Resistance** | Identifizierte Widerstands-Niveaus aus der AA-Analyse |
| **Indikatoren** | Name und aktueller Wert aktiver Indikatoren |

### 5.2 Visuelle Marker im Chart

Der Trade-Detail-Chart visualisiert die Trade-Daten durch farbige Marker und Linien:

#### Entry-Pfeil (cyan)

Ein **cyan-farbiger Pfeil** markiert den genauen Einstiegspunkt der Position auf der Zeitachse:
- Bei einem **BUY**: Pfeil zeigt nach oben
- Bei einem **SELL**: Pfeil zeigt nach unten

Der Pfeil befindet sich genau auf der Kerze, bei der der Trade eröffnet wurde.

#### Exit-Pfeil (amber/orange)

Ein **amber-/orangefarbener Pfeil** markiert den Ausstiegspunkt der Position:
- Bei geschlossenen BUY-Positionen: Pfeil zeigt nach unten (Verkauf zum Exit)
- Bei geschlossenen SELL-Positionen: Pfeil zeigt nach oben (Rückkauf zum Exit)
- Bei offenen Positionen: kein Exit-Pfeil sichtbar

#### SL-Linie (rot)

Eine **rote horizontale Linie** zeigt das Stop-Loss-Level an. Die Linie erstreckt sich über den Zeitraum der Position und zeigt visuell, wie nah der Preis dem Stop-Loss kam.

#### TP-Linie (grün)

Eine **grüne horizontale Linie** zeigt das Take-Profit-Level an. Die Linie zeigt, welches Ziel der Trade hatte.

#### S/R-Linien (Grau/gedämpft)

Horizontale Linien in gedämpften Grautönen zeigen die **Support- und Resistance-Niveaus**, die vom AA-Agent zum Zeitpunkt der Analyse identifiziert wurden. Diese Linien helfen zu verstehen, in welchem Kontext der Trade platziert wurde.

#### Analyse-Marker (Toggle)

Wenn die **„Show the Analyses"**-Checkbox aktiviert ist, werden **Analyse-Marker** auf dem Chart eingeblendet. Jeder Marker repräsentiert einen Analyse-Zyklus des AA-Agents, der in der Nähe des Trades stattfand.

Ein Klick auf einen Analyse-Marker öffnet das **AA Recommendation Popup** (siehe unten).

### 5.3 Chart-Steuerung

#### Timeframe-Buttons

| Button | Beschreibung |
|--------|-------------|
| **M5** | 5-Minuten-Kerzen — Details der unmittelbaren Ein- und Ausstiegsdynamik |
| **M15** | 15-Minuten-Kerzen — kurzfristige Struktur und Trend |
| **H1** | 1-Stunden-Kerzen — übergeordneter Trendkontext |

Nach dem Wechsel des Timeframes wird der Chart neu geladen. Die Kerzen-Anzahl passt sich an, um den Trade-Zeitraum plus Kontext abzudecken.

**Empfehlung:** Beginnen Sie die Nachanalyse bei H1, um den übergeordneten Kontext zu verstehen, dann wechseln Sie zu M15 und M5 für die Detail-Analyse des Einstiegs und Ausstiegs.

#### Indikatoren

Indikatoren können direkt im Orderbook-Chart hinzugefügt werden:

- **EMA** — Exponentieller Gleitender Durchschnitt mit konfigurierbarer Periode und eigenem Timeframe-Dropdown
- **RSI** — Relative Stärke Index in separatem Oszillator-Panel
- **ATR** — Average True Range für Volatilitäts-Kontext

Alle Perioden-Eingaben akzeptieren Ganzzahlen ≥ 1. Die Timeframe-Dropdowns erlauben einen abweichenden Berechnungs-Timeframe (z. B. EMA 20 auf H1 auch wenn der Chart auf M5 steht).

#### Print-Funktion

Der **Print**-Button öffnet den Druck-Dialog. Optionen:
- **Chart** einschließen (Checkbox)
- **Candle Data** einschließen (OHLCV-Daten)
- **Analysis** einschließen (AA-Analyse-Daten)

Nach Auswahl: Browser-Druckdialog mit optimierter HTML-Ansicht.

### 5.4 Show the Analyses — Analyse-Marker-Toggle

Die **„Show the Analyses"**-Checkbox im Chartbereich lädt und zeigt alle Analyse-Marker des AA-Agents für den angezeigten Zeitraum.

- **Aktiviert:** Alle AA-Analyse-Ergebnisse in der Nähe des Trades werden als farbige Marker auf dem Chart eingeblendet.
- **Deaktiviert:** Chart ohne Analyse-Marker, nur Preis und Indikatoren.

**Farbe der Marker** gibt einen schnellen Überblick über die jeweilige Entscheidung:
- Grün-Marker: BUY-Entscheidung
- Rot-Marker: SELL-Entscheidung
- Grau-Marker: HOLD-Entscheidung

Ein Klick auf einen Marker öffnet das AA Recommendation Popup.

---

## 6. AA Recommendation Popup

Das **AA Recommendation Popup** wird geöffnet durch Klick auf einen Analyse-Marker im Chart.

Es zeigt die vollständigen Detaildaten einer einzelnen Analyse-Empfehlung:

### 6.1 Kennzahlen-Grid (4 Spalten)

| Feld | Beschreibung |
|------|-------------|
| **Decision** | Die Handelsentscheidung: BUY, SELL oder HOLD |
| **Confidence** | Konfidenzwert der Entscheidung (0–100%) |
| **Order Start** | Signal-Zeitpunkt — wann das Signal erzeugt wurde |
| **Entry Quality** | Bewertung der Einstiegsqualität (z. B. Strong, Moderate, Weak) |

### 6.2 Decision JSON

Der vollständige strukturierte Output der AA-Entscheidung als JSON-Text:

```json
{
  "decision": "BUY",
  "confidence": 78,
  "entry": 1.08542,
  "stop_loss": 1.08320,
  "take_profit": 1.08920,
  "reasoning": "Der Preis hat einen klaren Aufwärtstrend auf H1...",
  "entry_quality": "Strong"
}
```

Ein **Copy-Button** kopiert den vollständigen JSON-Text in die Zwischenablage.

### 6.3 Decision Snapshot

Der vollständige **Market-Snapshot** zum Zeitpunkt der Entscheidung — die Marktdaten, die das LLM zur Entscheidungsfindung verwendet hat.

Dieser Snapshot ist besonders wertvoll für die Nachanalyse:
- Welche Kerzen hat das LLM gesehen?
- Welche Indikatorwerte lagen vor?
- Welche Swing Levels waren aktiv?

Ein **Copy-Button** kopiert den vollständigen Snapshot in die Zwischenablage.

**Wichtig:** Der Decision Snapshot ist nur vorhanden, wenn der AA-Agent im Snapshot-Modus läuft und die Daten gespeichert hat. Bei manchen Konfigurationen kann dieses Feld leer sein.

---

## 7. Typische Arbeitsabläufe

### 7.1 Tägliche P&L-Überprüfung

1. Orderbook öffnen.
2. Filter auf **geschlossen** setzen, Max Orders auf 20–50.
3. **Refresh** klicken.
4. Ergebnis-Spalte (P&L) durchsehen: Wo war Gewinn, wo Verlust?
5. Auf einzelne Trades klicken, um den Chart zu sehen: War der Trade-Kontext nachvollziehbar?
6. Bei Verlust-Trades: Analysis-Button klicken, um die AA-Begründung zu lesen.

### 7.2 Offene Positionen überwachen

1. Filter auf **offen** setzen.
2. **Refresh** klicken.
3. Prüfen: Wie nah ist der Preis am SL oder TP?
4. Chart auswählen und Chart-Timeframe auf M5 setzen — Momentum sehen.
5. Bei Bedarf: In den Broker-Account einloggen für direkte Kontrolle.

### 7.3 Warum wurde kein Trade ausgeführt?

Wenn ein erwarteter Trade nicht im Orderbook erscheint:

1. Filter auf **abgelehnt** setzen.
2. **Refresh** klicken — gibt es einen abgelehnten Eintrag für das erwartete Pair?
3. Falls ja: Analysis-Button öffnen — welcher Ablehnungsgrund wurde notiert?
4. Falls kein abgelehnter Eintrag: Filter auf **alle** setzen und nach dem Zeitraum suchen.
5. Falls gar kein Eintrag: Im Monitor prüfen — hat der AA-Agent überhaupt ein Signal generiert? (Agent Events Tab: `agent_signal_generated`?)

### 7.4 SYNC_DETECTED untersuchen

1. Eintrag mit `SYNC_DETECTED` in der Tabelle auswählen.
2. Chart öffnen — wann wurde die Position geschlossen?
3. Hat der Preis SL oder TP erreicht? (Linien im Chart prüfen)
4. Analysis öffnen — welche Analyse lag zugrunde?
5. In der Broker-Plattform den Schließgrund verifizieren (z. B. war es SL oder manuell).

### 7.5 Trade-Analyse für Optimierung

Um zu verstehen, ob der System-Prompt verbessert werden sollte:

1. Filter auf **geschlossen** setzen, längeren Zeitraum mit mehr Max Orders laden.
2. Verlust-Trades identifizieren (rote Ergebnis-Werte).
3. Für jeden Verlust-Trade:
   a. Chart öffnen, H1-Timeframe wählen — übergeordneter Kontext klar?
   b. „Show the Analyses" aktivieren — welche Signale wurden generiert?
   c. Analysis öffnen — was hat das LLM begründet?
   d. Gab es Muster? (z. B. alle Verluste bei starken News, alle Verluste in Ranging-Märkten)
4. Erkannte Muster als Grundlage für Prompt-Optimierungen nutzen.

---

## 8. Häufige Fragen

**F: Warum zeigt die Ergebnis-Spalte bei einer offenen Position einen Verlust, obwohl der Trade in die richtige Richtung geht?**

A: Das P&L bei offenen Positionen beinhaltet den Spread. Direkt nach Trade-Eröffnung ist die Position um den Spread-Betrag im Minus. Dies ist normal. Das P&L aktualisiert sich nach einem manuellen Refresh.

**F: Was bedeutet das Ausrufezeichen neben dem Pair?**

A: Das Ausrufezeichen zeigt an, dass der Eintrag noch keine Broker-Bestätigung erhalten hat. Die Zeitstempel (Von/Bis) können daher noch lokal und vorläufig sein (gelb angezeigt). Dies löst sich nach dem nächsten Broker-Sync (typischerweise innerhalb von Sekunden bis wenigen Minuten) auf.

**F: Die Schließgrund-Spalte zeigt SYNC_DETECTED. Ist das ein Fehler?**

A: Nein. SYNC_DETECTED ist kein Fehler — es ist ein informativer Status. Es bedeutet, dass OpenForexAI die Position nicht aktiv geschlossen hat, sondern beim nächsten Sync festgestellt hat, dass sie beim Broker nicht mehr existiert. Prüfen Sie die Broker-Plattform, um den tatsächlichen Schließgrund (z. B. SL/TP-Hit oder manuelles Schließen) zu erfahren.

**F: Kann ich im Orderbook manuell Trades schließen?**

A: Das Orderbook ist eine Inspektions- und Analyse-Seite, keine Trading-Seite. Zum manuellen Schließen von Positionen nutzen Sie direkt Ihre Broker-Plattform. OpenForexAI erkennt das manuelle Schließen beim nächsten Sync-Check automatisch.

**F: Warum sind manche Einträge gelb dargestellt?**

A: Gelbe Zeitstempel-Felder (Von/Bis) zeigen an, dass der Zeitstempel noch lokal ist und noch nicht vom Broker bestätigt wurde. Dies ist ein vorübergehender Zustand, der sich nach dem Broker-Sync auflöst.

**F: Ich sehe viele ABGELEHNT-Einträge. Was läuft falsch?**

A: Mehrere mögliche Ursachen: (1) Risikoprüfung schlägt an — z. B. wenn das konfigurierte Risiko-Maximum überschritten würde. (2) Der Broker lehnt Aufträge ab — z. B. bei unzureichendem Margin oder während gesperrter Handelszeiten. (3) Duplikat-Signal-Erkennung — wenn mehrere AA-Zyklen kurz hintereinander dasselbe Signal senden. Im Analysis-Popup des abgelehnten Eintrags finden Sie den spezifischen Ablehnungsgrund.
