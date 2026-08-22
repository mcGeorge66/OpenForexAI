[Zurück zu Action](ui.action.de.md)

# Chart Analyse — Handbuch

Die **Chart Analyse** ist ein vollständiges technisches Analyse-Werkzeug. Sie bietet einen interaktiven Kerzen-Chart mit Zeichenwerkzeugen, Indikatoren, Swing Levels und Analyst-Ansicht — und läuft in zwei Modi:

- **Freier Modus** (🔓, Standard): Sie steuern Pair, Broker, Timeframe, Kerzenanzahl, alle Indikatoren, Zeichenwerkzeuge und Swing-Level-Erkennung frei, ohne Bindung an eine Order. Der Chart aktualisiert sich alle 30 Sekunden automatisch; Indikatoren und Zeichnungen bleiben dabei erhalten.
- **Order-Fokus-Modus** (🔒): wird über den **Chart**-Button im Orderbook auf einer konkreten Order geöffnet. Der Chart lädt automatisch das Pair/Broker dieser Order und ein Kerzenfenster verankert um ihren Schließzeitpunkt, zeichnet Entry/Exit/SL/TP-Linien ein und friert ein (kein 30-Sekunden-Auto-Refresh mehr), damit sich der historische Zustand während der Analyse nicht verändert. Siehe [Abschnitt 11](#11-order-fokus-modus).

Beide Modi teilen sich einen eingebauten **KI Chart Assistenten** — ein Chat-Fenster, das Sie explizit öffnen (er öffnet sich nie von selbst) und das den sichtbaren Chart erklären und sogar selbst Marker/Zonen einzeichnen kann. Siehe [Abschnitt 12](#12-chart-assistent).

Nutzen Sie die Chart Analyse für freie technische Analyse, Session-Planung, Strategieentwicklung, visuelle Bestätigung dessen, was die Agenten "sehen", und die Nachbetrachtung konkreter Trades.

---

## 1. Obere Steuerleiste

Die Steuerleiste befindet sich direkt über dem Kerzen-Chart und enthält alle primären Bedienelemente für die Chart-Darstellung.

### 1.1 Pair-Dropdown

Das **Pair-Dropdown** wählt das Währungspaar für den Chart. Die Liste der verfügbaren Paare stammt aus den aktiven Broker-Verbindungen der Systemkonfiguration.

Typische Einträge:
- `EUR_USD`
- `GBP_USD`
- `USD_JPY`
- `AUD_USD`
- `USD_CAD`
- und weitere konfigurierte Paare

Nach der Auswahl eines neuen Pairs werden sofort neue Kerzen-Daten geladen und der Chart aktualisiert. Indikatoren und Zeichnungen bleiben erhalten, werden aber mit den neuen Daten neu berechnet.

### 1.2 Broker-Dropdown

Das **Broker-Dropdown** ist nur sichtbar, wenn mehr als ein Broker im System verbunden ist (z. B. sowohl `OXS_T` als auch `OXS_L`).

- Bestimmt, von welchem Broker die Kerzen-Daten geladen werden.
- Bei nur einem aktiven Broker wird dieses Dropdown ausgeblendet.
- Der gewählte Broker beeinflusst ausschließlich die Datenquelle — Zeichnungen und Indikatoren bleiben unverändert.

### 1.2a Modus-Anzeige (🔒 Order / 🔓 Frei)

Direkt nach dem Broker-Dropdown zeigt ein kleines Badge permanent, in welchem Modus sich die Seite befindet:

- **🔓 Frei** (grau) — freier Modus. Alles wird manuell gesteuert, nichts ist an eine Order gebunden.
- **🔒 Order** (indigo, klickbar) — Order-Fokus-Modus. Pair, Broker und Anchor wurden automatisch aus einer bestimmten Order übernommen (geöffnet über den **Chart**-Button im Orderbook). Beim Hovern zeigt ein Tooltip Pair/Richtung der Order.

Ein Klick auf das **🔒 Order**-Badge verlässt den Order-Fokus-Modus sofort und wechselt zurück in den freien Modus (Kerzenanzahl wird auf 200 zurückgesetzt, Anchor wird gelöscht, Auto-Refresh läuft wieder). Das ist der schnellste Weg, die Bindung an eine Order nach der Analyse wieder zu lösen, ohne Pair/Broker/Timeframe zu verlieren. Siehe [Abschnitt 11](#11-order-fokus-modus) für die vollständige Funktionsweise.

### 1.3 Timeframe-Buttons

Die **Timeframe-Buttons** wählen den Zeitrahmen der angezeigten Kerzen:

| Button | Bezeichnung | Beschreibung |
|--------|-------------|-------------|
| **M5** | 5-Minuten | Kurzfristige Preisbewegungen, primärer Agent-Trigger-Timeframe |
| **M15** | 15-Minuten | Kurzfristige Struktur, Momentum |
| **M30** | 30-Minuten | Mittelfristige Struktur |
| **H1** | 1-Stunde | Tagesstruktur, übergeordneter Trend |
| **H4** | 4-Stunden | Mehrtägige Trends |
| **D1** | Täglich | Übergeordnete Wochensicht |

Nach dem Wechsel des Timeframes werden sofort neue Kerzen-Daten geladen. Der Chart-Zoom wird auf eine sinnvolle Standardansicht zurückgesetzt.

### 1.4 Kerzenanzahl (Candle Count)

Das **Kerzenanzahl-Feld** bestimmt, wie viele Kerzen geladen und angezeigt werden.

- **Bereich:** 20 bis 2000 Kerzen
- **Standardwert:** 200 (typisch)
- **Eingabe:** Ganzzahl, angewendet nach Enter oder Verlassen des Feldes

**Auswirkungen:**
- Mehr Kerzen = längerer sichtbarer Zeitraum + langsamerer Ladevorgang
- Weniger Kerzen = schnellerer Ladevorgang, aber nur kurze Historie sichtbar
- Für tägliche Analyse: 200–500 Kerzen sind meist ausreichend
- Für übergeordnete Analyse (D1): 100–200 Kerzen zeigen mehrere Monate

### 1.4a Anchor-Feld

Ein `datetime-local`-Eingabefeld direkt nach der Kerzenanzahl, beschriftet mit **Anchor**. Leer gelassen (Standard) lädt der Chart die aktuellsten Kerzen — Live-Daten, die im 30-Sekunden-Takt aktualisiert werden. Setzen Sie einen Zeitpunkt, lädt der Chart stattdessen genau `Kerzenanzahl` Kerzen, die **an diesem Zeitpunkt enden** — und bleibt dort (keine "aktuellsten" Kerzen mehr, die sich unbemerkt einschleichen). Ein `×`-Button neben dem Feld erscheint, sobald ein Wert gesetzt ist, um ihn mit einem Klick wieder auf Live-Daten zurückzusetzen.

Dies ist derselbe Mechanismus, den der Order-Fokus-Modus automatisch verwendet — er befüllt genau dieses Feld mit dem Schließzeitpunkt der Order (siehe [Abschnitt 11](#11-order-fokus-modus)), anstatt es Ihnen händisch zu überlassen. Indikatoren, das DXY-Overlay und Swing Levels berücksichtigen jetzt ebenfalls diesen Anchor — vorher wurden sie immer gegen "jetzt" berechnet, selbst wenn der Chart selbst auf einen Zeitpunkt in der Vergangenheit verankert war (ein echter Bug, der damit behoben ist: früher konnte z. B. der heutige EMA-Wert neben Kerzen von letztem Monat angezeigt werden).

**Beispiel — Analyse eines verlorenen Trades:** Setzen Sie den Anchor auf den Schließzeitpunkt der Order (z. B. `2026-08-14T09:35`) und die Kerzenanzahl auf einen Wert, der den Trade komfortabel umspannt (z. B. 200), dann Reload — Sie sehen jetzt exakt die Preisbewegung rund um den Schluss, mit Indikatoren/Swing Levels, die zu diesem Zeitpunkt berechnet wurden, nicht heute. Noch einfacher: setzen Sie den Anchor gar nicht selbst — öffnen Sie den Trade über den **Chart**-Button im Orderbook, der dieses Feld für Sie setzt (Schließzeitpunkt + 1 Stunde) und zusätzlich Entry/Exit/SL/TP-Linien der Order einzeichnet, siehe [Abschnitt 11](#11-order-fokus-modus).

**Warnung:** Der Anchor ist — wie alle Order-/Kerzen-Zeitstempel im System — ein naiver Wanduhr-Zeitwert in der Zeitzone des Brokers, der nie über die Browser-Zeitzone konvertiert wird. Eine hier eingegebene Zeit bedeutet "Kerzen bis zu dieser Uhrzeit in der Broker-Zeitzone laden", nicht "in meiner lokalen Zeitzone" — relevant, wenn Ihr Rechner in einer anderen Zeitzone als der Broker steht.

### 1.5 Reload-Button

Der **Reload**-Button lädt die Kerzen-Daten manuell neu. Ein Spinner erscheint während des Ladens und der Button ist deaktiviert.

**Wichtig:** Der Chart aktualisiert sich alle 30 Sekunden automatisch. Das bedeutet:
- Neue Kerzen werden automatisch hinzugefügt.
- Indikatoren werden mit den neuen Kerzen neu berechnet.
- Manuell hinzugefügte Indikatoren bleiben bei Auto-Refresh erhalten.
- Der Reload-Button erzwingt einen sofortigen Refresh außer der Reihe.

**Wann manuell Reload klicken:**
- Nach einer Änderung der Kerzenanzahl oder des Anchors
- Nach einem Pair- oder Timeframe-Wechsel (wird automatisch ausgeführt)
- Wenn Sie sofort die neuesten Daten ohne Warten auf den Auto-Refresh sehen möchten

### 1.5a Geladener-Bereich-Diagnose-Badge

Direkt nach dem Reload-Button (und einer eventuellen Fehlermeldung) zeigt ein kleines Badge exakt, was geladen wurde, z. B. `200× 2026-08-14 06:00 → 2026-08-14 22:35`. Beim Hovern erscheint der vollständige erste/letzte Zeitstempel und die Kerzenanzahl. Damit lässt sich auf einen Blick unterscheiden, ob ein fehlender Marker an einem falschen geladenen Fenster liegt oder an etwas anderem.

Im Order-Fokus-Modus wird das Badge zusätzlich amber und zeigt eine Warnung, falls Start- und/oder Endzeitpunkt der fokussierten Order **außerhalb** des geladenen Kerzenfensters liegen (`⚠ Order-Start außerhalb!`, `⚠ Order-Ende außerhalb!` oder beides) — ein direktes Signal, dass die Kerzenanzahl erhöht oder der Anchor angepasst werden muss, da die Marker/Preislinien der Order sonst nichts haben, an dem sie auf dem Chart andocken können.

### 1.6 Auto-Refresh (30-Sekunden-Intervall)

Im **freien Modus** aktualisiert sich der Chart **automatisch alle 30 Sekunden** im Hintergrund. Dieser Auto-Refresh:
- Lädt neue Kerzen nach, wenn welche entstanden sind
- Aktualisiert alle Indikatoren mit den neuesten Daten
- **Löscht keine** manuell platzierten Zeichnungen
- **Löscht keine** konfigurierten Indikatoren

**Im Order-Fokus-Modus läuft der Auto-Refresh nicht.** Ein geschlossener historischer Trade braucht keine "neuesten Kerzen", und ein Refresh im Takt würde Pan/Zoom alle 30 Sekunden ohne Nutzen zurücksetzen — der Chart bleibt daher auf dem Kerzenfenster der Order eingefroren, bis Sie den Order-Fokus-Modus verlassen (Klick auf das 🔒-Badge). Siehe [Abschnitt 11](#11-order-fokus-modus). Ein manuell im freien Modus gesetzter Anchor stoppt den 30-Sekunden-Timer für sich genommen **nicht** — derselbe (vergangene) Zeitraum wird einfach erneut geladen, was in der Praxis keine sichtbare Änderung bewirkt, aber erklärt, warum der Lade-Spinner auf einem verankerten Chart trotzdem periodisch kurz aufblinkt.

### 1.6a Fit-Button

Direkt links vom Pan/Zoom-Umschalter. Passt **alle aktuell geladenen Kerzen** mit einem Klick in die sichtbare Chartbreite ein — das komplette geladene Fenster, randvoll, unabhängig davon, wie viele Kerzen das sind.

Das unterscheidet sich bewusst vom Standard-Zoom-Reset (z. B. nach einem Reload): dieser zeigt `min(konfigurierter Bereich, geladene Kerzen)` und kann ein größeres geladenes Fenster auf einen kleineren konfigurierten Bereich **zurückschneiden** (wurden z. B. 1000 Kerzen geladen, der konfigurierte Bereich ist aber 200, zeigt ein einfacher Reset nur die letzten 200). Fit ignoriert den konfigurierten Bereich komplett und streckt jede geladene Kerze über die volle Breite — nutzen Sie es direkt nach dem Laden eines großen historischen Fensters (z. B. über das Anchor-Feld), wenn Sie das Ganze auf einen Blick sehen wollen statt nur das Ende.

### 1.7 Pan/Zoom-Umschalter

Wechselt zwischen zwei Chart-Navigationsmodi:

- **Zoom-Modus (Standard):** Mausrad vergrößert/verkleinert den Chart (Zeit-Achse), Klicken und Ziehen verschiebt den Chart. Dies ist der Standard-Modus für tägliche Arbeit.
- **Pan-Modus (✋-Icon aktiv):** Freies Verschieben des Charts durch Klicken und Ziehen, ohne dass versehentlich ein Zeichenwerkzeug aktiviert wird.

### 1.8 Sessions-Checkbox

Die **Sessions**-Checkbox blendet farbige Session-Bänder auf dem Chart ein oder aus. Die Bänder zeigen die Handelszeiten der wichtigsten Forex-Sessions:

| Session | Farbe | Typische Handelszeiten (UTC) |
|---------|-------|------------------------------|
| **Sydney** | blau | 22:00 – 07:00 |
| **Tokyo** | amber/orange | 00:00 – 09:00 |
| **London** | grün | 08:00 – 17:00 |
| **New York** | orange | 13:00 – 22:00 |

Die Session-Überschneidungen (London/NY: 13:00–17:00 UTC) sind besonders volatil und für das Trading relevant.

### 1.9 Analyst-Checkbox

Die **Analyst**-Checkbox lädt und zeigt **Analyse-Marker** auf dem Chart — vergangene AA-Analysezyklen für das gewählte Pair, gebündelt je eine pro Kerze (fallen zwei Analysen in dieselbe Kerze, gewinnt die spätere).

- **U-Marker** (grün, ▲, unter der Kerze): `primary_bias` der Analyse war `BIAS_LONG` bzw. `BIAS_REVERSAL_LONG` — bullische Ausrichtung.
- **D-Marker** (rot, ▼, unter der Kerze): `primary_bias` war `BIAS_SHORT` bzw. `BIAS_REVERSAL_SHORT` — bearische Ausrichtung.
- **N-Marker** (grau, Kreis, unter der Kerze): alles andere (u. a. `BIAS_NEUTRAL`) — keine gerichtete Ausrichtung.

Ist eine Konfidenz gespeichert, erscheint sie als zweite Zeile (z. B. `U` + `85%`). Wichtig: der Marker zeigt nur die **Bias-Richtung** — ob der Agent tatsächlich ein Einstiegssignal (`order_start_signal`) ausgegeben hat, steht nicht in Farbe/Buchstabe, sondern erst im AA-Recommendation-Popup.

Ein Klick auf einen Marker öffnet das AA-Recommendation-Popup (Entscheidung, Konfidenz, Signal, Snapshot).

Die Analyst-Ansicht ist ein leistungsfähiges Werkzeug, um das Systemverhalten über die Zeit zu beobachten und zu verstehen, wann und warum bestimmte Entscheidungen getroffen wurden.

### 1.10 Print-Button

Öffnet den Print-Dialog (siehe Abschnitt 9).

### 1.11 → KB-Button

Speichert einen Markdown-Snapshot des aktuellen Charts im `ChartAnalysis`-Import-Bucket der Knowledgebase: ein Screenshot des Charts, die OHLCV-Daten der ausgewählten Kerze (falls vorhanden), die aktuellen Indikatorwerte, die Swing-Level-Liste (falls aktiviert) und den Text der ausgewählten Analyse (falls vorhanden). Nützlich, um einen schriftlichen Vermerk zu einem Setup anzulegen, ohne den Chart später komplett neu konfigurieren zu müssen. Zeigt für zwei Sekunden eine Bestätigung "✓ In Knowledgebase gespeichert" anstelle des Buttons.

### 1.12 Assistant-Button

Öffnet/schließt das schwebende **Chart Assistent**-Chatfenster. Standardmäßig geschlossen und bleibt es auch, wenn der Order-Fokus-Modus einen Trade lädt — Sie öffnen ihn immer explizit. Siehe [Abschnitt 12](#12-chart-assistent) für die Details.

---

## 2. Chartbereich

Der zentrale interaktive Chart ist der Hauptbereich der Seite.

**Unterstützte Interaktionen:**
- **Mausrad:** Zoom auf der Zeitachse (mehr oder weniger Kerzen sichtbar)
- **Klicken und Ziehen:** Chart verschieben (Pan)
- **Klick auf eine Kerze:** Kerze auswählen → Daten erscheinen in der rechten Spalte
- **Zeichenwerkzeug aktiv + Klick:** Zeichenpunkte setzen

**Dargestellte Inhalte:**
- Kerzen (OHLCV) — grün bei bullischer, rot bei bearischer Kerze
- Overlay-Indikatoren (EMA, SMA, BB, VWAP) — direkt auf dem Preis-Chart
- Oszillator-Indikatoren (RSI, ATR, SlopeE, SlopeS) — in separaten Panels unterhalb des Kerzen-Charts
- Zeichnungsobjekte (Linien, Fibonacci, Marker, Elliott-Wellen)
- Analyse-Marker (wenn Analyst aktiviert)
- Session-Bänder (wenn Sessions aktiviert)
- Swing Levels als horizontale Linien

---

## 3. Unteres Panel

Das untere Panel enthält alle Steuerungselemente für Indikatoren, Zeichenwerkzeuge und Kerzendaten. Es ist durch eine ziehbare Trennlinie am unteren Chartrand in der Höhe verstellbar (120–600 Pixel).

Das Panel ist in drei Spalten aufgeteilt.

---

## 4. Linke Spalte: Indikatoren

### 4.1 Indikatoren hinzufügen

Die Schaltflächen **EMA**, **SMA**, **RSI**, **ATR**, **BB**, **VWAP**, **SlopeE**, **SlopeS** fügen jeweils eine neue Indikator-Instanz hinzu. Mehrere Instanzen desselben Typs sind möglich.

### 4.2 Indikator-Zeile — Steuerelemente

Pro Indikator-Instanz gibt es folgende Bedienelemente:

| Element | Typ | Funktion |
|---------|-----|---------|
| **Auge-Icon** | Toggle | Indikator ein- oder ausblenden (ohne zu löschen) |
| **Farbfeld** | Color Picker | Farbe der Indikator-Linie oder des Oszillators |
| **Name** | Anzeige | Indikator-Typ (EMA, RSI usw.) |
| **Periode** | Zahlenfeld (1–500) | Berechnungsperiode |
| **Zeitrahmen** | Dropdown | Eigener Berechnungs-Timeframe (kann vom Chart-Timeframe abweichen) |
| **Linienstil** | Dropdown | Solid, Dashed, Dotted usw. |
| **Linienbreite** | Zahlenfeld (1–4) | Stärke der Linie |
| **Papierkorb** | Schaltfläche | Entfernt den Indikator |

---

## 5. Indikatoren — Vollständige Erklärung

### 5.1 EMA — Exponentieller Gleitender Durchschnitt

**Typ:** Overlay (auf dem Kerzen-Chart)

Der **EMA** (Exponential Moving Average) ist ein gewichteter gleitender Durchschnitt, der neueren Kursdaten mehr Gewicht beimisst als älteren. Er reagiert schneller auf Kursänderungen als der SMA.

**Darstellung:** Eine glatte Linie direkt auf dem Kerzen-Chart in der gewählten Farbe.

**Verwendung in OpenForexAI:**
- Trend-Identifikation: Kurs über EMA = bullisch, Kurs unter EMA = bearisch
- Dynamische Unterstützung/Widerstand: Der EMA-Level dient oft als Bounce-Niveau
- Signal-Bestätigung: AA-Agents verwenden EMA-Verhältnisse als Teil der Snapshot-Daten

**Typische Konfigurationen:**
- EMA(20) — kurzfristiger Trend
- EMA(50) — mittelfristiger Trend
- EMA(200) — langfristiger Trend (Haupt-Trendrichtung)
- Kombination: EMA(20) kreuzt EMA(50) nach oben = bullisches Kreuz

**Parameter:**
- Periode: 1–500 (Standard: 20)
- Zeitrahmen: Unabhängig vom Chart-Timeframe konfigurierbar

### 5.2 SMA — Einfacher Gleitender Durchschnitt

**Typ:** Overlay (auf dem Kerzen-Chart)

Der **SMA** (Simple Moving Average) berechnet den einfachen Durchschnitt der letzten N Schlusskurse mit gleichem Gewicht für alle Perioden.

**Darstellung:** Eine Linie auf dem Kerzen-Chart, typischerweise etwas glatter als ein vergleichbarer EMA (langsamer reagierend).

**Unterschied zu EMA:**
- SMA reagiert gleichmäßiger auf Kursbewegungen
- EMA reagiert schneller auf neue Kursdaten
- Für Trend-Identifikation über längere Zeiträume oft SMA bevorzugt

**Parameter:**
- Periode: 1–500 (Standard: 20)
- Zeitrahmen: Unabhängig konfigurierbar

### 5.3 RSI — Relative Stärke Index

**Typ:** Oszillator (separates Panel unterhalb des Charts)

Der **RSI** (Relative Strength Index) ist ein Momentum-Oszillator, der die Geschwindigkeit und Größe von Kursbewegungen misst. Er schwankt zwischen 0 und 100.

**Darstellung:** Eine Linie in einem separaten Panel unterhalb des Kerzen-Charts, mit horizontalen Referenzlinien.

**Interpretation:**

| RSI-Wert | Bedeutung |
|----------|-----------|
| > 70 | **Überkauft** — der Kurs könnte sich abschwächen oder umkehren |
| 50–70 | Bullischer Bereich |
| 50 | Neutralzone / Gleichgewicht |
| 30–50 | Bearischer Bereich |
| < 30 | **Überverkauft** — der Kurs könnte sich erholen oder umkehren |

**Wichtige Hinweise:**
- In Trending-Märkten kann der RSI lange im überkauften/überverkauften Bereich verbleiben.
- RSI-Divergenz (Kurs macht neues Hoch, RSI nicht) ist ein potenzielles Umkehrsignal.

**Parameter:**
- Periode: 1–500 (Standard: 14)
- Zeitrahmen: Unabhängig konfigurierbar

### 5.4 ATR — Average True Range

**Typ:** Oszillator (separates Panel unterhalb des Charts)

Der **ATR** (Average True Range) misst die durchschnittliche Preisvolatilität über N Perioden. Er gibt an, wie viele Pips der Markt typischerweise in einer Kerze bewegt.

**Darstellung:** Eine Linie in einem separaten Panel. Hoher ATR = hohe Volatilität, niedriger ATR = ruhiger Markt.

**Verwendung in OpenForexAI:**
- Stop-Loss-Kalibrierung: SL-Abstände werden oft als ATR-Multiplikator berechnet (z. B. 1.5 × ATR)
- Volatilitäts-Filter: Bei sehr niedrigem ATR kann das System ruhigere Marktphasen erkennen
- Swing-Level-Clustering: ATR wird für den Mindestabstand zwischen Swing Levels verwendet

**Parameter:**
- Periode: 1–500 (Standard: 14)
- Zeitrahmen: Unabhängig konfigurierbar

### 5.5 BB — Bollinger Bands

**Typ:** Overlay (auf dem Kerzen-Chart), Backend-berechnet

**Bollinger Bands** bestehen aus drei Linien:
- **Mittellinie:** SMA der gewählten Periode
- **Oberes Band:** Mittellinie + N × Standardabweichung
- **Unteres Band:** Mittellinie − N × Standardabweichung

**Darstellung:** Drei Linien auf dem Kerzen-Chart, die einen dynamischen Kanal um den Preis bilden.

**Interpretation:**
- Kurs nahe oberem Band = überdehnt (potenziell Rücklauf)
- Kurs nahe unterem Band = überdehnt nach unten (potenzieller Anstieg)
- Enge Bänder (Band Squeeze) = niedrige Volatilität, oft vor einem Ausbruch
- Breite Bänder = hohe Volatilität

**Hinweis:** BB werden im Backend berechnet — wie tatsächlich jeder Indikator in diesem Panel (EMA/SMA/RSI/ATR/SlopeE/SlopeS eingeschlossen): alle laufen über denselben `calculate_indicator`-Aufruf auf dem Server, es gibt keinen separaten client-seitigen Berechnungspfad.

### 5.6 VWAP — Volume-Weighted Average Price

**Typ:** Overlay (auf dem Kerzen-Chart), Backend-berechnet

Der **VWAP** (Volume-Weighted Average Price) ist der volumengewichtete Durchschnittspreis. Er gibt an, zu welchem Preis der Großteil des Handelsvolumens stattgefunden hat.

**Darstellung:** Eine Linie auf dem Kerzen-Chart.

**Verwendung:**
- Institutionelle Referenz: Viele institutionelle Trader verwenden VWAP als Referenz für faire Bewertung
- Kurs über VWAP = bullische Stimmung
- Kurs unter VWAP = bearische Stimmung
- VWAP als dynamische Unterstützung/Widerstand

**Hinweis:** VWAP wird — wie jeder andere Indikator in diesem Panel — im Backend berechnet und ist volumenabhängig. Die Qualität hängt von der Verfügbarkeit von Volumendaten des Brokers ab.

### 5.7 SlopeE — EMA-Steigung

**Typ:** Oszillator (separates Panel unterhalb des Charts)

**SlopeE** ist ein neuer Indikator in OpenForexAI. Er zeigt, wie steil der EMA steigt oder fällt — genauer gesagt: wie viele Pips sich der EMA pro Kerze bewegt.

**Darstellung:** Eine Linie in einem separaten Oszillator-Panel mit einer **Nulllinie** als Referenz.

**Interpretation:**

| SlopeE-Wert | Bedeutung |
|-------------|-----------|
| **Positiv (über Nulllinie)** | EMA steigt — Aufwärtstrend aktiv |
| **Nahe Null** | EMA ist flach — kein klarer Trend |
| **Negativ (unter Nulllinie)** | EMA fällt — Abwärtstrend aktiv |
| **Nulllinien-Kreuzung von unten nach oben** | Potenzieller Trendwechsel: Trend dreht von bearisch auf bullisch |
| **Nulllinien-Kreuzung von oben nach unten** | Potenzieller Trendwechsel: Trend dreht von bullisch auf bearisch |

**Smooth-Period-Feld:**

Neben der Standard-Periode gibt es ein zusätzliches **Smooth-Period-Feld** (amber/orange hervorgehoben, Standard: 3). Dieses Feld steuert die EMA-Glättung der berechneten Slope-Werte selbst.

- **Kleiner Smooth-Wert (z. B. 3):** Slope reagiert schnell auf Steigungsänderungen, aber mit mehr Rauschen.
- **Größerer Smooth-Wert (z. B. 10):** Slope ist geglätteter, reagiert langsamer, aber zeigt klarere Trends.

**Führender Indikator mit smooth_period=10:**

Ein besonderes Merkmal von SlopeE: Mit einem `smooth_period`-Wert von 10 zeigt der Indikator Trendwechsel **ca. 2 Kerzen früher** als die eigentliche EMA-Kreuzung oder ein visuell erkennbarer Trendwechsel im Chart. Dies macht ihn zu einem **führenden Indikator** (Leading Indicator) für Trendwechsel.

**Beispiel SlopeE(20) auf H1 mit smooth=10:**

```
Kerzennummer  SlopeE-Wert   Bedeutung
     1        -0.8          EMA fällt stark
     2        -0.5          EMA fällt weniger stark
     3        -0.2          EMA fällt kaum noch
     4         0.0          Nulllinien-Kreuzung → Trendwechselsignal!
     5        +0.3          EMA steigt leicht
     6        +0.7          EMA steigt deutlich
```

Am Ende von Kerze 4 (Nulllinien-Kreuzung) zeigt der SlopeE das Trendwechselsignal, während die EMA selbst auf dem Chart noch keine eindeutige Richtungsänderung zeigt. Das gibt Ihnen 1–2 Kerzen Vorsprung für eine Einstiegsentscheidung.

**Kombination mit EMA:**
Die effektivste Verwendung ist die Kombination von EMA(20) als Overlay mit SlopeE(20) als Oszillator. Sie sehen den aktuellen EMA-Kurs UND die Impulsrichtung des EMA gleichzeitig.

**Parameter:**
- Periode: 1–500 (Standard: 20) — wie bei EMA
- Zeitrahmen: Unabhängig konfigurierbar
- Smooth-Period: 1–50 (Standard: 3, amber hervorgehoben)

### 5.8 SlopeS — SMA-Steigung

**Typ:** Oszillator (separates Panel unterhalb des Charts)

**SlopeS** ist identisch zu SlopeE, aber bezogen auf den **SMA** statt den EMA.

**Darstellung und Interpretation:** Genau wie SlopeE — positiv = SMA steigt, negativ = SMA fällt, Nulllinien-Kreuzung = Trendwechselsignal.

**Unterschied zu SlopeE:**
- SlopeS reagiert etwas langsamer auf Kursänderungen (da SMA träger ist als EMA)
- SlopeS-Trendwechselsignale sind etwas verzögerter, aber ggf. robuster bei Rauschen
- Für kurze Perioden (5–15) ist SlopeE oft bevorzugt
- Für längere Perioden (50–200) kann SlopeS stabiler sein

**Parameter:**
- Periode: 1–500 (Standard: 20)
- Zeitrahmen: Unabhängig konfigurierbar
- Smooth-Period: 1–50 (Standard: 3, amber hervorgehoben)

---

## 6. Swing Levels

### 6.1 Was sind Swing Levels?

**Swing Levels** sind lokale Preis-Hochs (Swing Highs = SH) und Preis-Tiefs (Swing Lows = SL), die als horizontale Linien auf dem Chart dargestellt werden. Sie repräsentieren potenzielle Unterstützungs- und Widerstandsniveaus, bei denen der Preis in der Vergangenheit umgekehrt hat.

Swing Levels sind ein zentrales Element der AA-Analyse: Sie fließen als Support/Resistance-Levels in den Snapshot ein und werden vom LLM bei der Entscheidungsfindung berücksichtigt.

### 6.2 Swing Level Steuerelemente

| Element | Typ | Funktion |
|---------|-----|---------|
| **Checkbox** (Header) | Toggle | Aktiviert/deaktiviert alle Swing Levels auf dem Chart |
| **Zeitrahmen** | Dropdown | Kerzen-Timeframe für die Swing-Berechnung |
| **Count** | Zahlenfeld (1–20) | Maximale Anzahl angezeigter Swing Levels |
| **ATR Period** | Zahlenfeld (1–200) | ATR-Periode für den Clustering-Algorithmus |
| **Gap (ATR Multiple)** | Zahlenfeld (0–5, Schritt 0.1) | Mindestabstand zwischen Levels in ATR-Einheiten |
| **Width** | Zahlenfeld (1–5) | Linienbreite der Swing-Linien |
| **Style** | Dropdown | Linienstil (Solid, Dashed, Dotted usw.) |
| **Reload** | Schaltfläche | Berechnet Swing Levels neu und lädt sie |

### 6.3 Sortierung der Swing Levels

Die Swing Levels können nach zwei Sortierungsoptionen angezeigt werden:

- **Next (Nächste):** Die Levels werden nach ihrer Nähe zum aktuellen Preis sortiert. Die relevantesten Levels (unmittelbar oberhalb und unterhalb des aktuellen Preises) werden zuerst angezeigt.
- **Prominent (Markant):** Die Levels werden nach ihrer historischen Bedeutung sortiert — je häufiger ein Level als Wendepunkt diente, desto weiter oben in der Liste.

### 6.4 Visible/All

- **Visible:** Zeigt nur Swing Levels, die im aktuellen Chart-Sichtbereich liegen.
- **All:** Zeigt alle berechneten Swing Levels, auch wenn sie außerhalb des aktuellen Sichtbereichs liegen.

### 6.5 HL/OC

Steuert, ob die Swing-Berechnung auf **High/Low** (HL) oder **Open/Close** (OC) der Kerzen basiert:

- **HL (High/Low):** Klassische Methode — Swing Highs basieren auf den Kerzen-Hochs, Swing Lows auf den Kerzen-Tiefs. Dies erfasst die gesamte Preisspanne inkl. Dochten.
- **OC (Open/Close):** Conservative Methode — nur der Körper der Kerze wird berücksichtigt. Dochten werden ignoriert. Erzeugt weniger, aber ggf. bedeutungsvollere Levels.

### 6.6 ATR-Gap (Mindestabstand)

Der **Gap**-Parameter steuert den Mindestabstand zwischen zwei Swing Levels in ATR-Einheiten. Levels, die näher beieinander liegen als der Gap-Wert, werden zusammengefasst (Clustering).

- **Gap = 0:** Kein Clustering — alle gefundenen Levels werden einzeln angezeigt, auch wenn sie sehr nah beieinander liegen. Dies kann zu vielen kleinen Clustern führen.
- **Gap = 1.0:** Ein Mindestabstand von 1× ATR zwischen Levels. Typischer Standardwert für eine sinnvolle Filterung.
- **Gap = 2.0:** Nur deutlich voneinander getrennte Levels werden angezeigt.

### 6.7 Swing Level Liste

Unterhalb der Steuerelemente wird die Liste der berechneten Swing Levels angezeigt:

| Symbol | Bedeutung |
|--------|-----------|
| **Roter Punkt** | Swing High (SH) — Widerstandsniveau |
| **Grüner Punkt** | Swing Low (SL) — Unterstützungsniveau |
| **Gelber Punkt** | Konfluenz (SH/SL) — Level das sowohl als Hoch als auch als Tief identifiziert wurde |

Jeder Eintrag zeigt den exakten Preis-Level.

---

## 7. Mittlere Spalte: Zeichenwerkzeuge

### 7.1 Stil-Steuerelemente

Globale Stil-Einstellungen für neu erstellte Zeichnungen:

| Element | Funktion |
|---------|---------|
| **Farbe** | Linienfarbe für neue Zeichnungen |
| **Linienstil** | Solid, Dashed, Dotted usw. |
| **Linienbreite** | 1–4 |
| **Füllfarbe** | Für Flächenobjekte (Rechteck, Kanal, Fibonacci) |
| **Füll-Opazität** | 0–1, Schritt 0.05 |

### 7.2 Linien-Werkzeuge

| Werkzeug | Beschreibung | Klick-Punkte |
|---------|-------------|-------------|
| **Horizontale Linie** | Durchgehende horizontale Preislinie | 1 |
| **Vertikale Linie** | Durchgehende vertikale Zeitlinie | 1 |
| **Ray** | Halbgerade — beginnt an einem Punkt und erstreckt sich nach rechts | 1 |
| **Ext. Line** | Linie durch zwei Punkte, die in beide Richtungen unendlich verlängert wird | 2 |
| **Trendlinie** | Linie zwischen genau zwei Punkten — endet an den Punkten, wird nicht verlängert (im Gegensatz zu Ext. Line) | 2 |
| **Kanal** | Paralleler Kanal — Trendlinie + parallele Rücklauflinie | 3 |

### 7.3 Fibonacci-Werkzeuge

| Werkzeug | Beschreibung |
|---------|-------------|
| **Fibonacci Retracement** | Klassisches Fibonacci-Retracement (0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100%) |
| **Fibonacci Extension** | Extension-Levels über 100% hinaus für Kursziele |
| **Fibonacci Fan** | Winkellinien basierend auf Fibonacci-Verhältnissen |
| **Fibonacci Zeitzonen** | Vertikale Linien in Fibonacci-Zeitabständen |

### 7.4 Marker

| Werkzeug | Beschreibung |
|---------|-------------|
| **Pfeil nach oben** | Grüner Aufwärts-Pfeil zur Markierung bullischer Punkte |
| **Pfeil nach unten** | Roter Abwärts-Pfeil zur Markierung bearischer Punkte |
| **↔ Measure** | Zwei-Klick-Werkzeug: zeichnet eine halbtransparente Box zwischen zwei Punkten mit Endmarkierungen, beschriftet mit **Kerzenanzahl** und **Pip-Abstand** (z. B. `12c +34.5p`). Der schnellste Weg, "wie viele Pips/Kerzen zwischen diesen zwei Punkten" zu beantworten, ohne selbst zu rechnen. |

### 7.5 Erweiterte Werkzeuge

| Werkzeug | Beschreibung | Hinweis |
|---------|-------------|---------|
| **Rechteck** | Rechteck-Bereich auf dem Chart | Mit Füllung (transparente Farbe empfohlen) |
| **Textlabel** | Freitext-Label an beliebiger Chartposition | Zeilenumbruch mit `|` |
| **Pitchfork** | Andrews-Pitchfork (Median-Linie + zwei Parallellinien) | 3 Punkte: Swing-Hoch, Swing-Tief, zweites Swing-Hoch |
| **Elliott-Welle** | Multi-Punkt Elliott-Wellen-Zeichnung | 3–9 Punkte, Impuls oder Korrektur |

### 7.6 Elliott-Wellen-Zeichnung

Die **Elliott-Wellen**-Zeichnung ist das komplexeste Werkzeug:

| Option | Werte | Beschreibung |
|--------|-------|-------------|
| **Points** | 3–9 | Anzahl der Wellenpunkte |
| **Modus** | `1-2-3-4-5` / `A-B-C` | Impuls-Welle (5-Wellen) oder Korrektur-Welle (3-Wellen) |
| **Done** | Button (auch in Kopfleiste) | Welle manuell abschließen vor dem letzten Punkt |

Während der Elliott-Wellen-Zeichnung erscheint ein `✕`-Symbol in der Kopfleiste zum Abbrechen und ein **„Done"**-Button zum Abschließen.

### 7.7 Zeichnungsliste

Alle platzierten Zeichnungen werden in einer Liste unterhalb der Werkzeuge angezeigt. Pro Zeichnung:

| Element | Funktion |
|---------|---------|
| **Auge-Icon** | Zeichnung ein-/ausblenden |
| **Farbpunkt** | Zeigt aktuelle Farbe |
| **Name** | Zeichnungstyp (z. B. „Trendlinie", „Fibonacci Retracement") |
| **Aufklappen** | Öffnet Detail-Editor für diese Zeichnung |
| **Papierkorb** | Löscht die Zeichnung |

**Detail-Editor (aufgeklappt):**
- Alle Stil-Steuerelemente (Farbe, Stil, Breite, Füllung, Opazität)
- Bei Textlabel: Textfeld und Schriftgröße (8–72)
- Pro Punkt (P1, P2, ...): Preis-Eingabe und Zeitpunkt (Datum + Uhrzeit)

---

## 8. Rechte Spalte: Kerzendaten & Analyst

### 8.1 Kerzendaten

Bei Klick auf eine Kerze im Chart zeigt die rechte Spalte die vollständigen Daten dieser Kerze:

| Feld | Beschreibung |
|------|-------------|
| **Zeitpunkt** | Datum und Uhrzeit der Kerze |
| **Open** | Eröffnungspreis |
| **High** | Hochpunkt |
| **Low** | Tiefpunkt |
| **Close** | Schlusskurs |
| **Volume** | Handelsvolumen (wenn vom Broker verfügbar) |
| **Indikatoren** | Indikatorwerte zum Zeitpunkt der Kerze (farbig, nach Indikator-Farbe) |
| **DXY** | DXY (US Dollar Index) Daten: Close, Richtung (UP/DOWN), Korrelation mit dem gewählten Pair |

Die **DXY-Daten** sind besonders nützlich für USD-basierte Paare, um zu verstehen, ob eine Bewegung vom Dollar oder von der Gegenwährung getrieben wird.

### 8.2 Analyst-Ansicht

| Element | Funktion |
|---------|---------|
| **Checkbox** (Header) | Aktiviert/deaktiviert Analyse-Marker auf dem Chart |
| **Analyse-Schaltfläche** | Öffnet das AA-Recommendation-Popup für die ausgewählte Kerze |

Der **Analyse-Schaltfläche**-Button öffnet das Popup mit allen AA-Analyse-Daten für die ausgewählte Kerze (falls eine Analyse für diese Kerze in der Datenbank vorhanden ist).

---

## 9. Print-Dialog

Der Print-Dialog wird über den **Print**-Button in der Kopfleiste geöffnet.

| Option | Funktion |
|--------|---------|
| **Chart** | Checkbox: Chart-Screenshot im Ausdruck einschließen |
| **Candle Data** | Checkbox: Kerzendaten der ausgewählten Kerze einschließen |
| **Analysis** | Checkbox: Analyse-Daten einschließen (sofern vorhanden) |
| **Cancel** | Dialog schließen ohne zu drucken |
| **Print** | Browser-Druckdialog mit generierter HTML-Seite öffnen |

---

## 10. AA-Recommendation-Popup

Das **AA-Recommendation-Popup** wird geöffnet durch:
- Klick auf den Analyse-Button in der rechten Spalte (für die ausgewählte Kerze)
- Klick auf einen Analyse-Marker im Chart

**Inhalt:**

4-Spalten-Grid mit Kennzahlen:
- **Decision** — das Entscheidungsfeld der AA für diesen Zyklus. Dies ist ein direkter Durchgriff auf das Feld, das die AA selbst im JSON-Output geschrieben hat — kein festes Enum im Code. Je nach aktivem Prompt-Profil des Agenten sind Werte wie `BIAS_LONG`/`BIAS_SHORT`/`NEUTRAL`, `OPEN_BUY`/`OPEN_SELL`/`SKIP_*` oder ein verschachteltes State-Objekt möglich — als Freitext lesen, nicht gegen eine feste Liste.
- **Confidence** — Konfidenzwert 0–100 % aus dem LLM-Output
- **Order Start** — der `order_start_signal`-Wert (Einstiegsbereitschaft, z. B. YES/NO — **kein** Zeitstempel)
- **Entry Quality** — Einstiegsqualitätsbewertung

**Decision JSON / Analysetext:**
Vollständige strukturierte Ausgabe der LLM-Analyse. Copy-Button zum Kopieren.

**Market Snapshot:**
Vollständiger Markt-Snapshot zum Zeitpunkt der Entscheidung (wenn vorhanden). Copy-Button zum Kopieren.

---

## 11. Order-Fokus-Modus

Der Order-Fokus-Modus bindet die Chart Analyse an einen konkreten historischen Trade. Man erreicht ihn über das **Orderbook**: Klick auf den **Chart**-Button (LineChart-Icon) einer Order-Zeile — das wechselt den Action-Tab zur Chart Analyse und lädt diese Order. Das ist ein eigener Einstiegspunkt, getrennt vom **AI**-Button im Orderbook (der öffnet ein leichtgewichtiges "Ask AI"-Investigate-Popup ohne die Ansicht zu wechseln) — nutzen Sie **Chart**, wenn Sie das volle Charting-Werkzeug (Indikatoren, Zeichenwerkzeuge, Swing Levels) gegen den Trade brauchen, und **AI**, wenn nur eine schnelle Antwort ohne Ansichtswechsel gewünscht ist.

### Was beim Öffnen automatisch passiert

1. Pair und Broker der Order werden geladen und ersetzen die vorherige Auswahl.
2. Das **Anchor**-Feld ([Abschnitt 1.4a](#14a-anchor-feld)) wird auf den Schließzeitpunkt der Order + 1 Stunde gesetzt (bzw. den verfügbaren "End"-Zeitpunkt, falls die Order nicht geschlossen wurde) — ein fester Versatz, keine dynamisch berechnete Fenstergröße.
3. Die **Kerzenanzahl** bleibt unverändert (Standard 200 bei erster Nutzung) — genau so viele Kerzen werden bis zum Anchor geladen.
4. Sobald die Kerzen geladen sind, passt der Chart seinen sichtbaren Bereich einmalig an, damit die Marker der Order tatsächlich sichtbar sind (dies wiederholt sich nicht bei jedem weiteren Reload, damit Sie danach frei zoomen/verschieben können).
5. Entry-, Exit-, Stop-Loss- und Take-Profit-Preislinien werden eingezeichnet, zusammen mit hervorgehobenen **Start**/**End**-Trade-Markern an den Open-/Close-Kerzen der Order.
6. Das Modus-Badge im Header wechselt auf **🔒 Order**.

Der **Chart Assistent öffnet sich dabei nicht automatisch** — auch hier öffnen Sie ihn weiterhin explizit über den Assistant-Toggle, wenn Sie zur Order etwas fragen möchten (siehe [Abschnitt 12](#12-chart-assistent)).

### Was im Fokus-Modus anders ist

- **Auto-Refresh stoppt** — siehe [Abschnitt 1.6](#16-auto-refresh-30-sekunden-intervall). Das Fenster bleibt eingefroren, bis Sie den Fokus-Modus verlassen — das ist der Sinn: der Kontext eines geschlossenen Trades soll sich während der Analyse nicht verändern.
- Das **Anchor**-Feld bleibt sichtbar und editierbar — Sie können es manuell verschieben (z. B. um weiter vor den Einstieg zu blicken), ohne den Fokus-Modus zu verlassen; nur das Modus-Badge und der zusätzliche Order-Kontext des Assistenten bleiben an die fokussierte Order gebunden, nicht an den exakten Anchor-Wert.
- Das **Geladener-Bereich-Diagnose-Badge** ([Abschnitt 1.5a](#15a-geladener-bereich-diagnose-badge)) wird amber und warnt, falls Start- und/oder Endzeitpunkt der Order außerhalb des geladenen Fensters liegen — Kerzenanzahl erhöhen oder Anchor anpassen, bis die Warnung verschwindet, falls der gesamte Trade sichtbar sein soll.
- Öffnen Sie den Assistenten im Fokus-Modus, erhält er automatisch den vollständigen Order-Kontext — Richtung, Signal-Konfidenz, Requested-/Fill-/Close-Preise und -Zeiten, Stop-Loss/Take-Profit, Schließgrund und Ergebnis, die kurze Entry-Begründung, den **vollständigen Original-Analysetext**, den strukturierten Decision Context, die Analysis Overlays und den rohen Market Context Snapshot — plus einen Satz read-only Investigations-Tools, die er sonst nicht hat (`get_order_trace`, `get_agent_decisions`, `get_agent_config`, `get_ec_config`, `get_ec_runs`, `get_order`/`get_order_book`, `get_candles`/`calculate_indicator`/`get_swing_levels`). Siehe [Abschnitt 12](#12-chart-assistent).

### Order-Fokus-Modus verlassen

Klick auf das **🔒 Order**-Badge im Header. Das entfernt die fokussierte Order, setzt die Kerzenanzahl auf 200 und den Anchor auf leer (Live-Daten) zurück und startet den 30-Sekunden-Auto-Refresh wieder — Pair, Broker und Timeframe bleiben unverändert, da Sie das gleiche Instrument im freien Modus vermutlich weiter betrachten möchten.

### Beispiel: Analyse eines verlorenen Trades

**Ziel:** genau verstehen, was der AA-Agent vor dem Schließen eines verlorenen EURUSD-Trades gesehen hat, und ob der Schluss sinnvoll war.

1. **Orderbook** öffnen, den verlorenen Trade finden, dessen **Chart**-Button klicken.
2. Die Chart Analyse öffnet im Order-Fokus-Modus: EURUSD lädt, verankert auf den Schließzeitpunkt des Trades, mit bereits eingezeichneten Entry/SL/TP/Exit-Linien und Start/End-Markern.
3. **Assistant**-Toggle klicken, um den Chart Assistenten zu öffnen — er hat bereits den vollständigen Analysetext, Decision Context und Market Snapshot der Order, sodass direkt gefragt werden kann: *"Warum wurde dieser Trade ausgestoppt — war die SL-Platzierung angesichts der Volatilität beim Einstieg sinnvoll?"*
4. Bezieht sich die Antwort auf eine bestimmte Kerze oder ein Level, den Assistenten bitten, es einzuzeichnen (z. B. *"zeichne eine Zone um die Konsolidierung direkt vor dem Einstieg"*), statt Koordinaten aus einer Textbeschreibung selbst abzuleiten.
5. Zum Abschluss auf das **🔒 Order**-Badge klicken, um in den freien Modus zurückzukehren, ohne die EURUSD/H1-Auswahl zu verlieren.

Denselben verankerten Zustand könnten Sie auch manuell erreichen (Anchor selbst im freien Modus auf den Schließzeitpunkt setzen) — der **Chart**-Button im Orderbook erledigt das aber mit einem Klick und zeichnet zusätzlich die Preislinien/Marker der Order ein. Bevorzugen Sie ihn daher, wann immer eine konkrete Order vorliegt.

## 12. Chart Assistent

Der Chart Assistent ist ein in die Chart Analyse eingebautes KI-Chat-Fenster. Er kann erklären, was aktuell auf dem Chart geladen ist, und — im Order-Fokus-Modus — auch die konkrete Order. Anders als andere Assistenten im System ist er nicht rein lesend: er kann über denselben Tool-Calling-Mechanismus wie die Simulation/Prompt-Workbench-"Sandbox"-Tools direkt auf dem Chart zeichnen.

Er **öffnet sich nie von selbst** — Klick auf den **Assistant**-Toggle-Button (oben rechts in der Kopfleiste) öffnet ihn, ein weiterer Klick schließt ihn. Das Öffnen ändert nichts am Chart selbst.

### Das Fenster

Der Assistent wird als **schwebendes Fenster** dargestellt, nicht als angedocktes Panel — das ist bewusst so: ein angedocktes Seitenpanel würde sich die Breite mit dem Chart per Flexbox teilen, aber die Chart-Canvas verkleinert sich nicht in jedem Fall zuverlässig mit, sodass ein Panel den Chart optisch überlappen könnte. Ein schwebendes Fenster nimmt an diesem Layout gar nicht teil.

- **Verschieben** über die Kopfzeile ("Chart Assistant").
- **Größe ändern** über den kleinen Griff unten rechts (Minimum 320×280px).
- Standardmäßig oben rechts positioniert, passend zur Fenstergröße.
- Ist eine Order fokussiert, zeigt die Kopfzeile eine kompakte Zusammenfassung (`EURUSD BUY · Fill 1.0842 · Close 1.0798`), damit beim Verschieben des Fensters der Bezug nicht verloren geht.
- Schließen über das **✕** in der Kopfzeile oder erneut über den Assistant-Toggle — in beiden Fällen geht der Chatverlauf verloren (im Panel gibt es zusätzlich einen expliziten **Delete**-Button, um den Verlauf ohne Schließen zu löschen).

### Was er kann

- **Preisverlauf, Trends, Support/Resistance und Indikatoren erklären** für das aktuell geladene Pair/Timeframe/die geladenen Kerzen.
- **Selbst auf dem Chart zeichnen**, statt Koordinaten in Textform zu beschreiben — er bevorzugt das beim Erklären von "warum", weil ein Marker eindeutig ist und eine Textbeschreibung von "wo" auf einem Chart nicht:
  - `candle_marker` — ein einzelner Pfeil+Label auf einer Kerze.
  - `zone_marker` — eine beschriftete Zone über einen Kerzenbereich (z. B. eine Support/Resistance-Zone, eine Konsolidierungsrange).
  - `trade_marker` — ein hypothetisches oder historisches Entry/Exit-Paar zur Veranschaulichung eines Setups.
  - `get_annotation` — etwas nachschlagen, das früher in derselben Konversation markiert wurde.

  Diese werden mit dem **gleichen Rendering wie im Simulation-Tab** gezeichnet — ein hier gesetzter Marker sieht identisch aus und verhält sich identisch zu einem dort gesetzten.
- **Eine Notiz zum Verhalten eines Trading-Agenten** über Konversationen hinweg mit `assessment_memory` (get/set) speichern, verschlüsselt über die Agent-ID — nützlich, damit ein wiederkehrendes Muster nicht bei jeder Frage neu abgeleitet werden muss.
- **Nur im Order-Fokus-Modus** stehen zusätzliche read-only Investigations-Tools zur Verfügung (vollständige Liste in [Abschnitt 11](#11-order-fokus-modus)) — dieselbe Lese-Reichweite, die das frühere per-Order "Investigate"-Popup hatte, sodass beim Zusammenführen in den einheitlichen Assistenten keine Fähigkeit verloren ging. Fragen wie *"was hat diesen Trade geschlossen — die AA selbst, ein Trailing-Stop oder ein Risk-Guard?"* kann er anhand der Open- und Close-Entscheidungsketten beantworten, die tatsächliche Live-Konfiguration von Agent/EventComposer nachschlagen und andere Orders zum Vergleich heranziehen.

### Antworten lesen

Unter jeder Antwort kann eine **Tools:**-Zeile stehen, die genau die für diese Antwort tatsächlich ausgeführten Tool-Aufrufe auflistet (z. B. `trade_marker(open) OK`, `assessment_memory FAILED`) — abgeleitet aus den tatsächlichen Tool-Call-Events der Antwort, nicht aus dem Antworttext geraten. So lässt sich immer nachvollziehen, ob eine behauptete Aktion ("Ich habe die Zone markiert") tatsächlich passiert ist.

Lange Antworten werden standardmäßig in einer begrenzten, scrollbaren Box (ca. 15 Zeilen) mit **Show more/Show less** und einem **Copy**-Button angezeigt — der vollständige Text ist immer im DOM vorhanden, die Begrenzung betrifft nur die sichtbare Höhe.

### Wissenswertes / Fehlerbehebung

- Kann die Persona-/Instruktionsdatei (`config/llm_contexts/chart_analysis_assistant.md`) nicht geladen werden, erscheint ein amber Banner oben im Panel mit dem Hinweis, dass Antworten dadurch schlechter ausfallen können — der Chat funktioniert trotzdem weiter, nur ohne die vollständigen Instruktionen.
- Ein `404`-Fehler beim Senden bedeutet, dass der Backend-Prozess die Chat-Route des Assistenten noch nicht kennt — das erfordert einen **Backend-Neustart** (Python hat kein Hot-Reload für neu hinzugefügte Routen), kein bloßes Neuladen der Seite.
- Eingabefeld und Send-Button sind deaktiviert, solange kein Pair geladen ist — auf einem leeren Chart gibt es noch nichts zu besprechen.
- Nichts, was hier eingegeben wird, verändert die gespeicherten Daten der Order (falls fokussiert) — es ist eine Konversation über den Chart/die Order, keine Bearbeitung ihres gespeicherten Datensatzes.

---

## 13. Typische Arbeitsabläufe

### 13.1 Tägliche Marktanalyse

1. Chart Analyse öffnen, gewünschtes Pair wählen.
2. **H1-Timeframe** wählen — übergeordneten Trendkontext sehen.
3. **EMA(50)** und **EMA(200)** als Overlays hinzufügen — Haupttrendrichtung identifizieren.
4. **RSI(14)** hinzufügen — Momentum prüfen.
5. **SlopeE(20) smooth=10** hinzufügen — zeigt Trendimpuls-Änderungen frühzeitig.
6. **Swing Levels** aktivieren — Key-Levels identifizieren.
7. **Sessions** aktivieren — relevante Handelsfenster sehen.
8. Auf **M15** wechseln — detaillierte kurzfristige Struktur.
9. **Analyst** aktivieren — vergangene AA-Entscheidungen im Kontext sehen.

### 13.2 Swing Level Optimierung

Wenn zu viele oder zu wenige Levels angezeigt werden:

1. **Count** reduzieren (z. B. auf 5), um nur die wichtigsten Levels zu sehen.
2. **Gap** erhöhen (z. B. auf 1.5), um Cluster zusammenzufassen.
3. **Timeframe** der Swing Levels ändern (z. B. H1-Levels auf M15-Chart zeigen).
4. **ATR Period** anpassen — höhere ATR-Periode = stabilere Gap-Berechnung.

### 13.3 SlopeE als Frühwarnsystem verwenden

1. **EMA(20)** auf H1 hinzufügen.
2. **SlopeE(20)** mit **smooth_period=10** hinzufügen.
3. Beobachten Sie: Wenn SlopeE die Nulllinie kreuzt, aber der EMA noch flach verläuft, ist ein Trendwechsel in Vorbereitung.
4. Warten Sie auf Bestätigung durch den EMA-Verlauf und ggf. RSI.
5. Kombinieren Sie SlopeE-Kreuzungen mit Swing Level Bounces für höhere Konfidenz.

### 13.4 Nachbetrachtung eines verlorenen Trades (Order-Fokus + Anchor + Assistent)

**Ziel:** Nachvollziehen, was ein Agent vor einem Verlust-Trade gesehen hat und ob der Ausstieg sinnvoll war — ohne den historischen Chart-Zustand händisch zu rekonstruieren.

1. **Orderbook** öffnen, den Trade suchen, dessen **Chart**-Button klicken — schneller und vollständiger als den Anchor selbst zu setzen, da zusätzlich Entry/Exit/SL/TP-Linien und Start/End-Marker der Order eingezeichnet werden.
2. Das **Geladener-Bereich-Diagnose-Badge** prüfen — bei amberfarbener Warnung Kerzenanzahl erhöhen oder Anchor anpassen, bis Start und Ende der Order im geladenen Fenster liegen.
3. Den **Assistant** öffnen und das Setup erklären lassen — er hat bereits den vollständigen Analysetext, Decision Context und Market Snapshot der Order, kein Copy-Paste nötig.
4. Nach dem Schluss fragen (*"was hat das hier tatsächlich geschlossen — die AA, ein Trailing-Stop oder ein Risk-Guard?"*) — im Order-Fokus-Modus kann er dank der zusätzlichen Investigations-Tools die echte Ursachenkette beantworten statt nur den gespeicherten `close_reason` zu wiederholen.
5. Alles, worauf sich die Antwort bezieht, vom Assistenten auf dem Chart markieren lassen, statt Koordinaten aus Text abzuleiten.
6. Zum Abschluss auf das **🔒 Order**-Badge klicken, um zum freien Modus auf demselben Pair zurückzukehren.

Details zu den einzelnen Schritten: [Abschnitt 11](#11-order-fokus-modus) und [Abschnitt 12](#12-chart-assistent).
