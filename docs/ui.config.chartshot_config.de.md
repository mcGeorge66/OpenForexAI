[Zurück zu Config](ui.config.de.md)

# Chartshot Config — Handbuch

Die Seite **Chartshot Config** verwaltet benannte Vorlagen für das `chartshot`-Tool. Dieses Tool rendert einen Kerzenchart serverseitig (ohne Browser, via `mplfinance`) als PNG-Bild und übergibt es dem LLM als Bild-Anhang — der einzige Weg, wie ein Agent einen Chart tatsächlich **visuell sieht**, statt ihn nur aus Zahlenreihen zu rekonstruieren.

**Wann lohnt sich das?** Reine Zahlenanalyse (OHLC-Werte, Indikator-Zahlen) ist für ein LLM oft ausreichend, aber manche Muster — z. B. ein sauberer Doppel-Boden, eine Flagge, ein Ausbruch aus einem erkennbaren Kanal — lassen sich in Textform nur umständlich beschreiben, während ein Vision-fähiges LLM sie auf einem Bild sofort erkennt. Chartshot lohnt sich also vor allem dann, wenn der Prompt explizit visuelle Chartmuster ansprechen soll, nicht für reine Kennzahlen-Auswertung (dafür reichen `calculate_indicator`/`get_candles`).

Gespeichert unter `config/system.json5` → `chartshot`.

---

## 1. Wie das Bild beim LLM ankommt

Das Tool schreibt immer eine Datei auf die Festplatte und gibt einen Bild-Marker-String zurück:

| `output_mode` | Marker | Verhalten |
|---|---|---|
| `keep` | `image[pfad]` | Datei bleibt nach dem LLM-Aufruf erhalten |
| `temp` | `imagetmp[pfad]` | Datei wird nach dem LLM-Aufruf gelöscht |

Der LLM-Adapter erkennt diese Marker automatisch im Tool-Ergebnis und hängt das Bild als echten Bild-Anhang an die nächste LLM-Anfrage an — es muss nichts weiter konfiguriert werden.

**Achtung:** Ein Bild an das LLM zu schicken ist deutlich teurer (und oft langsamer) als reiner Text. `chartshot` sollte in einem Snapshot sparsam eingesetzt werden — meist reicht **ein** Chart-Bild pro Analyse-Zyklus, zusätzlich zu den ohnehin vorhandenen Text-Daten, statt mehrerer Bilder für verschiedene Timeframes.

---

## 2. Linke Spalte: Vorlagenliste

| Element | Funktion |
|---------|---------|
| **Output directory** | Zielverzeichnis für gerenderte Bilddateien (Standard: `data/chartshots`), gilt für alle Vorlagen gemeinsam. |
| **Vorlagenliste** | Alle benannten Konfigurationen. `default` kann nicht gelöscht werden — sie ist der Fallback, wenn ein Tool-Aufruf einen unbekannten Namen angibt. |
| **„new config name" + [+]** | Legt eine neue, leere Vorlage mit diesem Namen an. |

**Empfehlung:** Für jeden Anwendungsfall eine eigene, sprechend benannte Vorlage anlegen statt alles über `default` laufen zu lassen — z. B. `trend_h1` (wenig Indikatoren, H1-Fokus für Trendkontext) und `entry_m5` (EMA + Swing Levels, M15/M5-Fokus für die eigentliche Einstiegsentscheidung). So kann ein Snapshot-Profil gezielt das passende Bild anfordern, statt für jeden Zweck denselben, zu vollen oder zu leeren Chart zu bekommen.

---

## 3. Rechte Spalte: Vorlagen-Editor

### 3.1 Kopfzeile

`AI Assistant`-Button öffnet den eingebetteten [AI-Assistant](ui.config.ai_assistant.de.md)-Chat mit Kontext zur aktuell bearbeiteten Vorlage. `Reload` lädt neu vom Server, `Save` schreibt die gesamte `chartshot`-Konfiguration zurück nach `system.json5`. `Delete` entfernt die aktuell gewählte Vorlage — außer `default`.

### 3.2 Output mode

- **temp** — Bilddatei wird nach der LLM-Verarbeitung gelöscht (Standard, spart Speicherplatz).
- **keep** — Bilddatei bleibt auf der Festplatte erhalten.

**Empfehlung:** `temp` für den Live-Betrieb verwenden — bei mehreren Agenten und häufigen Zyklen sammeln sich sonst schnell sehr viele Bilddateien an. `keep` eignet sich für die Entwicklungsphase einer neuen Vorlage, wenn man nachträglich genau nachvollziehen möchte, was das LLM tatsächlich gesehen hat.

### 3.3 Chart style

`dark` oder `light` — steuert Hintergrund- und Rasterfarben des gerenderten Charts. Hat keinen bekannten Effekt auf die Analysequalität des LLM; reine Geschmacksfrage bzw. Frage der Lesbarkeit beim manuellen Prüfen der Bilder (Abschnitt 4).

### 3.4 Description

Freitext, der dem LLM-Prompt angehängt wird, wenn dieses Bild in einem Snapshot verwendet wird.

**Beispiel:** „Dieser Chart zeigt EURUSD M15 mit EMA 20 und wichtigen Swing Levels. Fokus auf die Reaktion an der markierten Support-Zone — insbesondere, ob der Preis diese Zone mit abnehmendem Momentum oder mit einem klaren Bruch verlässt."

**Empfehlung:** Die Description sollte konkret sagen, *worauf* das LLM achten soll, nicht nur beschreiben, was im Bild zu sehen ist (das Bild zeigt das ja bereits). „Achte besonders auf X" ist wertvoller als „Dieser Chart zeigt EURUSD".

### 3.5 Indicators

Gleiches Panel wie in Chart Analysis / Prompt Workbench. Details siehe [Chart Analysis Handbuch](ui.action.chart_analysis.de.md#5-indikatoren--vollständige-erklärung).

**Warnung — nicht überladen:** Jeder zusätzliche Indikator macht das Bild optisch dichter. Zu viele Overlays/Oszillatoren auf einmal (z. B. vier Indikatoren gleichzeitig) können ein Vision-Modell eher verwirren als unterstützen, ähnlich wie einen Menschen ein überladener Chart schwerer lesbar macht. Für eine Vorlage lieber 1–2 klar erkennbare Overlays wählen, die tatsächlich zur Fragestellung passen.

### 3.6 Swing Levels

Gleiches Panel wie in Chart Analysis / Prompt Workbench.

### 3.7 Preview (JSON)

Am Ende des Editors: schreibgeschützte Vorschau des exakten `system.json5`-Eintrags, der beim Speichern für diese Vorlage geschrieben wird — nützlich, um vor dem Speichern kurz zu prüfen, ob z. B. ein Indikator versehentlich doppelt eingetragen wurde.

---

## 4. Live-Vorschau rendern

Der aufklappbare **Preview**-Bereich oben im Editor erlaubt es, die aktuell bearbeitete Vorlage sofort gegen echte Marktdaten zu testen, ohne zu speichern:

| Feld | Funktion |
|------|---------|
| **Agent** | Wählt einen konfigurierten Agenten — übernimmt dessen Pair und Broker automatisch. |
| **Broker** / **Pair** | Können auch manuell überschrieben werden. |
| **Timeframe** | Chart-Zeitrahmen für die Vorschau. |
| **Candles** | Anzahl der Kerzen (10–500). |
| **Run** | Rendert das Bild serverseitig mit den aktuell im Editor stehenden Einstellungen (auch ungespeicherte Änderungen) und zeigt es direkt an. |

**Empfehlung:** Nach jeder Änderung an Indikatoren/Swing Levels **Run** klicken, bevor man speichert — es ist deutlich schneller, ein zu unübersichtliches Bild hier zu erkennen und zu korrigieren, als es erst live in einem echten Agenten-Zyklus zu bemerken (wo man das Bild nicht ohne Weiteres zu Gesicht bekommt, siehe Warnung unten).

**Warnung — man sieht das Bild in Produktion normalerweise nicht selbst:** Im Live-Betrieb geht das gerenderte Bild direkt an das LLM, nicht an die Benutzeroberfläche. Ob eine Vorlage tatsächlich brauchbare Bilder erzeugt, lässt sich am zuverlässigsten hier in der Preview prüfen — im Zweifel testweise `output_mode: keep` setzen, einen Zyklus laufen lassen und die Datei danach manuell im `output_dir` öffnen.

Die Vorschau-Datei wird nach der Anzeige automatisch vom Server gelöscht (unabhängig vom `output_mode` der Vorlage).

---

## 5. Typischer Ablauf

1. Neue Vorlage anlegen oder `default` bearbeiten.
2. Indikatoren und Swing Levels sparsam einstellen (siehe Warnung in Abschnitt 3.5).
3. `Description` so formulieren, dass sie dem LLM sagt, worauf es beim Betrachten achten soll (siehe Beispiel in Abschnitt 3.4).
4. Im Preview-Bereich Agent/Pair/Timeframe wählen und **Run** klicken — Ergebnis anschauen, ist das Bild klar lesbar oder zu voll?
5. `Save` klicken.
6. Die Vorlage per Name in einem `tool_blocks`-Eintrag (Snapshot Config oder Prompt Workbench) beim `chartshot`-Tool referenzieren.
7. Nach dem ersten echten Einsatz: bei Unsicherheit, ob das Bild wie gewünscht ankommt, kurzzeitig `output_mode: keep` setzen und die erzeugte Datei im `output_dir` prüfen.
