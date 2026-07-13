[Zurück zu Action](ui.action.de.md)

# Chart Analyse — Handbuch

Die **Chart Analyse** ist ein vollständiges technisches Analyse-Werkzeug. Sie bietet einen interaktiven Kerzen-Chart mit Zeichenwerkzeugen, Indikatoren, Swing Levels und Analyst-Ansicht. Im Gegensatz zum Orderbook ist sie nicht an eine spezifische Trade-Position gebunden — sie dient der freien technischen Analyse zu jedem gewünschten Zeitpunkt und für jedes verfügbare Währungspaar.

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

### 1.5 Reload-Button

Der **Reload**-Button lädt die Kerzen-Daten manuell neu. Ein Spinner erscheint während des Ladens und der Button ist deaktiviert.

**Wichtig:** Der Chart aktualisiert sich alle 30 Sekunden automatisch. Das bedeutet:
- Neue Kerzen werden automatisch hinzugefügt.
- Indikatoren werden mit den neuen Kerzen neu berechnet.
- Manuell hinzugefügte Indikatoren bleiben bei Auto-Refresh erhalten.
- Der Reload-Button erzwingt einen sofortigen Refresh außer der Reihe.

**Wann manuell Reload klicken:**
- Nach einer Änderung der Kerzenanzahl
- Nach einem Pair- oder Timeframe-Wechsel (wird automatisch ausgeführt)
- Wenn Sie sofort die neuesten Daten ohne Warten auf den Auto-Refresh sehen möchten

### 1.6 Auto-Refresh (30-Sekunden-Intervall)

Der Chart aktualisiert sich **automatisch alle 30 Sekunden** im Hintergrund. Dieser Auto-Refresh:
- Lädt neue Kerzen nach, wenn welche entstanden sind
- Aktualisiert alle Indikatoren mit den neuesten Daten
- **Löscht keine** manuell platzierten Zeichnungen
- **Löscht keine** konfigurierten Indikatoren
- Ist für den Benutzer kaum wahrnehmbar (kein Flackern)

### 1.7 Pan/Zoom-Umschalter

Wechselt zwischen zwei Chart-Navigationsmodi:

- **Zoom-Modus (Standard):** Mausrad vergrößert/verkleinert den Chart (Zeit-Achse), Klicken und Ziehen verschiebt den Chart. Dies ist der Standard-Modus für tägliche Arbeit.
- **Pan-Modus (✋-Icon aktiv):** Freies Verschieben des Charts durch Klicken und Ziehen, ohne dass versehentlich ein Zeichenwerkzeug aktiviert wird.

### 1.8 Sessions-Checkbox

Die **Sessions**-Checkbox blendet farbige Session-Bänder auf dem Chart ein oder aus. Die Bänder zeigen die Handelszeiten der wichtigsten Forex-Sessions:

| Session | Farbe | Typische Handelszeiten (UTC) |
|---------|-------|------------------------------|
| **Sydney** | blau-grau | 22:00 – 07:00 |
| **Tokyo** | rot/orange | 00:00 – 09:00 |
| **London** | grün | 08:00 – 17:00 |
| **New York** | blau | 13:00 – 22:00 |

Die Session-Überschneidungen (London/NY: 13:00–17:00 UTC) sind besonders volatil und für das Trading relevant.

### 1.9 Analyst-Checkbox

Die **Analyst**-Checkbox lädt und zeigt **Analyse-Marker** auf dem Chart — vergangene AA-Entscheidungen für das gewählte Pair und den gewählten Timeframe.

- **Aktiviert:** Für jede Kerze, bei der ein AA-Agent eine Analyse durchgeführt hat, erscheint ein farbiger Marker.
- **Grüne Marker:** BUY-Entscheidung
- **Rote Marker:** SELL-Entscheidung
- **Graue Marker:** HOLD-Entscheidung

Ein Klick auf einen Marker öffnet das Analyse-Detail-Popup (Entscheidung, Konfidenz, Signal, Snapshot).

Die Analyst-Ansicht ist ein leistungsfähiges Werkzeug, um das Systemverhalten über die Zeit zu beobachten und zu verstehen, wann und warum bestimmte Entscheidungen getroffen wurden.

### 1.10 Print-Button

Öffnet den Print-Dialog (siehe Abschnitt 8).

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

**Hinweis:** BB werden im Backend berechnet. Die Berechnung erfolgt serverseitig und die Ergebnisse werden an den Chart übertragen.

### 5.6 VWAP — Volume-Weighted Average Price

**Typ:** Overlay (auf dem Kerzen-Chart), Backend-berechnet

Der **VWAP** (Volume-Weighted Average Price) ist der volumengewichtete Durchschnittspreis. Er gibt an, zu welchem Preis der Großteil des Handelsvolumens stattgefunden hat.

**Darstellung:** Eine Linie auf dem Kerzen-Chart.

**Verwendung:**
- Institutionelle Referenz: Viele institutionelle Trader verwenden VWAP als Referenz für faire Bewertung
- Kurs über VWAP = bullische Stimmung
- Kurs unter VWAP = bearische Stimmung
- VWAP als dynamische Unterstützung/Widerstand

**Hinweis:** VWAP wird im Backend berechnet und ist volumenabhängig. Die Qualität hängt von der Verfügbarkeit von Volumendaten des Brokers ab.

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
| **Ray** | Halbgerade — beginnt an einem Punkt und erstreckt sich nach rechts | 2 |
| **Trendlinie** | Linie zwischen zwei Punkten (kein Ende) | 2 |
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
| **Analyse-Schaltfläche** | Öffnet das Analyse-Detail-Modal für die ausgewählte Kerze |

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

## 10. Analyse-Detail-Popup

Das **Analyse-Detail-Popup** wird geöffnet durch:
- Klick auf den Analyse-Button in der rechten Spalte (für die ausgewählte Kerze)
- Klick auf einen Analyse-Marker im Chart

**Inhalt:**

4-Spalten-Grid mit Kennzahlen:
- **Decision** — BUY, SELL oder HOLD
- **Confidence** — Konfidenzwert 0–100%
- **Order Start Signal** — Zeitpunkt des generierten Signals
- **Entry Quality** — Einstiegsqualitätsbewertung

**Decision JSON / Analysetext:**
Vollständige strukturierte Ausgabe der LLM-Analyse. Copy-Button zum Kopieren.

**Market Snapshot:**
Vollständiger Markt-Snapshot zum Zeitpunkt der Entscheidung (wenn vorhanden). Copy-Button zum Kopieren.

---

## 11. Typische Arbeitsabläufe

### 11.1 Tägliche Marktanalyse

1. Chart Analyse öffnen, gewünschtes Pair wählen.
2. **H1-Timeframe** wählen — übergeordneten Trendkontext sehen.
3. **EMA(50)** und **EMA(200)** als Overlays hinzufügen — Haupttrendrichtung identifizieren.
4. **RSI(14)** hinzufügen — Momentum prüfen.
5. **SlopeE(20) smooth=10** hinzufügen — zeigt Trendimpuls-Änderungen frühzeitig.
6. **Swing Levels** aktivieren — Key-Levels identifizieren.
7. **Sessions** aktivieren — relevante Handelsfenster sehen.
8. Auf **M15** wechseln — detaillierte kurzfristige Struktur.
9. **Analyst** aktivieren — vergangene AA-Entscheidungen im Kontext sehen.

### 11.2 Swing Level Optimierung

Wenn zu viele oder zu wenige Levels angezeigt werden:

1. **Count** reduzieren (z. B. auf 5), um nur die wichtigsten Levels zu sehen.
2. **Gap** erhöhen (z. B. auf 1.5), um Cluster zusammenzufassen.
3. **Timeframe** der Swing Levels ändern (z. B. H1-Levels auf M15-Chart zeigen).
4. **ATR Period** anpassen — höhere ATR-Periode = stabilere Gap-Berechnung.

### 11.3 SlopeE als Frühwarnsystem verwenden

1. **EMA(20)** auf H1 hinzufügen.
2. **SlopeE(20)** mit **smooth_period=10** hinzufügen.
3. Beobachten Sie: Wenn SlopeE die Nulllinie kreuzt, aber der EMA noch flach verläuft, ist ein Trendwechsel in Vorbereitung.
4. Warten Sie auf Bestätigung durch den EMA-Verlauf und ggf. RSI.
5. Kombinieren Sie SlopeE-Kreuzungen mit Swing Level Bounces für höhere Konfidenz.
