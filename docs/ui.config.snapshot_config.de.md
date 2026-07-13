[Zurück zu Config](ui.config.de.md)

# Snapshot Config

Snapshot Config definiert, welche Marktdaten gesammelt, wie sie transformiert und wie sie zu einem strukturierten Kontextblock zusammengesetzt werden, der vor jedem Analysezyklus in den LLM-Prompt injiziert wird. Ein Snapshot-Profil erspart dem AA-Agenten eigene Tool-Aufrufe zur Analysezeit: Die gesamte Datenbeschaffung und Vorverarbeitung erfolgt in einer dedizierten Pipeline, und der fertige Snapshot kommt als bereite Benutzernachricht an.

## Referenzdokumente
- [Snapshot-Konfigurationsleitfaden](snapshot-config-guide.de.md)
- [Snapshot-Transformers](snapshot-transformers.de.md)
- [Snapshot-Hilfsfunktionen](snapshot-helper-functions.de.md)

---

## Inhaltsverzeichnis

1. [Die Snapshot-Pipeline](#die-snapshot-pipeline)
2. [Kopfleiste](#kopfleiste)
3. [Profil-Grunddaten](#profil-grunddaten)
4. [Snapshot Tool Blocks](#snapshot-tool-blocks)
5. [Die Standard-aa_default_v1-Tool-Blocks](#die-standard-aa_default_v1-tool-blocks)
6. [Calculation Blocks](#calculation-blocks)
7. [Die Standard-aa_default_v1-Calculation-Blocks](#die-standard-aa_default_v1-calculation-blocks)
8. [Assembly Transform](#assembly-transform)
9. [Aktionsschaltflächen](#aktionsschaltflächen)
10. [Live-Vorschau und Validierung](#live-vorschau-und-validierung)
11. [Execute-Vorschau](#execute-vorschau)
12. [Details zu Calculation Blocks](#details-zu-calculation-blocks)
13. [Snapshot-Probleme beheben](#snapshot-probleme-beheben)

---

## Die Snapshot-Pipeline

Die Snapshot-Pipeline läuft einmal pro Analysezyklus, ausgelöst wenn der AA-Agent einen `m5_agent_trigger` empfängt. Die Schritte:

**Schritt 1 — Tool-Block-Ausführung (parallel)**
Alle aktivierten Tool-Blöcke laufen gleichzeitig. Jeder Block ruft ein einzelnes Tool auf (z.B. `get_candles`, `calculate_indicator`, `get_swing_levels`) mit seinen konfigurierten Argumenten. Die Rohausgabe wird in `tool_outputs[output_key]` gespeichert.

**Schritt 2 — Tool-Block-Transform**
Wenn ein Tool-Block ein `transform_script` hat, läuft es unmittelbar nachdem das Tool zurückgekehrt ist und wandelt die Rohausgabe in das gewünschte Format um.

**Schritt 3 — Calculation-Block-Ausführung (sequentiell)**
Calculation-Blöcke laufen in Abhängigkeitsreihenfolge. Jeder Block liest aus `tool_outputs` und/oder früheren Calculation-Ergebnissen, führt reine Python-Berechnungen durch (keine externen Aufrufe) und speichert sein Ergebnis in `calcs[block_id]`.

**Schritt 4 — Assembly**
Das Assembly-Transform-Skript läuft als letztes. Es liest alle `tool_outputs` und `calcs` und erstellt das finale Snapshot-Dictionary. Dieses wird als JSON serialisiert und als Benutzernachricht an das LLM übergeben.

**Schritt 5 — Prompt-Injektion**
Der Decision Input Prefix-Text wird dem serialisierten Snapshot-JSON vorangestellt. Der kombinierte String bildet den Benutzerturn der LLM-Konversation.

---

## Kopfleiste

| Element | Funktion |
|---------|----------|
| **Snapshot Profile** | Dropdown: Profil zum Anzeigen oder Bearbeiten auswählen |
| **Execute Context Agent** | Dropdown: Agent auswählen, dessen Kontext für die Execute-Vorschau verwendet wird |
| **Refresh** | Profile und Agentenliste vom Backend neu laden |
| **New Empty Profile** | Alle Felder leeren für ein neues Profil |
| **Execute** | Aktuelles Profil live gegen den Kontext des gewählten Agenten ausführen und Ergebnisse anzeigen |

---

## Profil-Grunddaten

### Name

Eindeutiger Bezeichner des Profils. Wird durch das `snapshot_profile`-Feld in Agent Config referenziert. Pflichtfeld. Konvention: `aa_default_v1`, `ba_default_v1`, `eurusd_aggressive_v2`.

### Strategy Aggressiveness

Steuert, wie aggressivitätssensitive Calculation-Blöcke ihre Ergebnisse interpretieren.

| Wert | Bedeutung |
|------|-----------|
| `CONSERVATIVE` | Engere Gate-Schwellenwerte, geringere Toleranz für mehrdeutige Signale |
| `BALANCED` | Standard — ausgewogene Schwellenwerte für die meisten Bedingungen |
| `AGGRESSIVE` | Weitere Schwellenwerte, höhere Toleranz für Grenzsignale |

Calculation-Blöcke, die aggressivitätsbewusst sind, passen ihre Ausgabe-Labels und Boolean-Flags basierend auf dieser Einstellung an. Der `entry_gates`-Block ist der primäre Verbraucher dieser Einstellung.

### Description

Freitextdokumentationsfeld. Hat keinen Einfluss auf das Laufzeitverhalten. Zur Beschreibung des beabsichtigten Anwendungsfalls, Versionshinweisen oder Unterschieden zu anderen Profilen verwenden.

### Decision Input Prefix

Text, der dem Snapshot-JSON vorangestellt wird, wenn es in den LLM-Prompt injiziert wird. Standardwert:

```
Runtime-prepared market decision snapshot for current cycle. Analyze the following structured data and provide your trading decision:
```

Dieser Prefix teilt dem LLM mit, was es empfangen wird. Anpassen, um die Rahmung der Daten durch das LLM zu leiten. Der Prefix wird pro Profil gespeichert, so dass verschiedene Profile das LLM unterschiedlich instruieren können.

### Short Timeframe / Long Timeframe

| Feld | Standard | Optionen |
|------|----------|---------|
| Short Timeframe | M15 | M5, M15, M30, H1, H4, D1 |
| Long Timeframe | H1 | M5, M15, M30, H1, H4, D1 |

Diese Werte stehen Tool-Blöcken und Calculation-Skripten als `SHORT_TF` bzw. `LONG_TF` zur Verfügung. Tool-Block-Argumente, die diese Sonderwerte verwenden, lösen sie zur Laufzeit auf.

---

## Snapshot Tool Blocks

Tool-Blöcke sind die Datenbeschaffungsschicht. Jeder Block ruft ein Tool auf und speichert seinen Output. Blöcke laufen parallel — es gibt keine Sequenzierung zwischen ihnen.

### Block hinzufügen

1. Tool aus dem „Add Tool"-Dropdown wählen
2. „Add Tool" klicken
3. Block ID, Output Key und Argumente ausfüllen
4. Optional Transform-Skript schreiben

### Block-Felder

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| **Block ID** | Text | Interner Bezeichner. Wird von Calculation-Blöcken über `tool_outputs[id]` referenziert. snake_case. Muss im Profil eindeutig sein. |
| **Tool** | Dropdown | Das aufzurufende Tool. Wechsel setzt Argumente zurück und löscht das Transform-Skript. |
| **Output Key** | Text | Schlüssel unter dem das Tool-Ergebnis in `tool_outputs` gespeichert wird. Oft identisch mit Block ID. |
| **Enabled** | Checkbox | Wenn deaktiviert, wird der Block vollständig übersprungen. Andere Blöcke die von seiner Ausgabe abhängen erhalten `None`. |
| **Argumente** | Dynamisch | Aus dem JSON-Schema des Tools generiert. Text-, Zahlen- und Dropdown-Felder je nach Argumenttyp. |
| **Transform Script** | Code-Editor | Python, das nach der Tool-Rückkehr ausgeführt wird. Eingabe: `raw_output`. Ausgabe: muss `result` zugewiesen werden. |
| **Test** | Schaltfläche | Führt den Block isoliert mit den Daten des Execute Context Agent aus. Zeigt Roh- und transformierte Ausgabe nebeneinander. |
| **Remove** | Schaltfläche | Löscht diesen Block aus dem Profil. |

### Spezielle Argumentwerte

| Wert | Löst sich auf zu |
|------|-----------------|
| `SHORT_TF` | Die Short-Timeframe-Einstellung des Profils (z.B. `M15`) |
| `LONG_TF` | Die Long-Timeframe-Einstellung des Profils (z.B. `H1`) |

---

## Die Standard-aa_default_v1-Tool-Blocks

Das Standardprofil `aa_default_v1` enthält folgende Tool-Blöcke:

### m5_recent

| Feld | Wert |
|------|------|
| Tool | `get_candles` |
| Output Key | `m5_recent` |
| Zeitrahmen | `M5` |
| Anzahl | `5` |
| Zweck | Letzte 4 geschlossene M5-Kerzen für Mikro-Level-Kontext |

### m15_recent

| Feld | Wert |
|------|------|
| Tool | `get_candles` |
| Output Key | `m15_recent` |
| Zeitrahmen | `SHORT_TF` (M15 Standard) |
| Anzahl | `20` |
| Zweck | 20 M15-Kerzen für Trend-, Struktur-, S/R- und RSI-Berechnungen |

Die primäre Kerzenquelle für die meisten Calculation-Blöcke.

### h1_recent

| Feld | Wert |
|------|------|
| Tool | `get_candles` |
| Output Key | `h1_recent` |
| Zeitrahmen | `LONG_TF` (H1 Standard) |
| Anzahl | `60` |
| Zweck | 60 H1-Kerzen für höheren Zeitrahmen-Kontext, strukturelle S/R und H1-Trend |

60 Kerzen = ca. 2,5 Handelwochen H1-Daten.

### ema_fast

| Feld | Wert |
|------|------|
| Tool | `calculate_indicator` |
| Output Key | `ema_fast` |
| Indikator | `EMA` |
| Zeitrahmen | `SHORT_TF` (M15) |
| Periode | `3` |
| History | `3` |
| Zweck | Schneller EMA auf M15 für kurzfristige Trendrichtung |

### ema_slow

| Feld | Wert |
|------|------|
| Tool | `calculate_indicator` |
| Output Key | `ema_slow` |
| Indikator | `EMA` |
| Zeitrahmen | `SHORT_TF` (M15) |
| Periode | `8` |
| History | `3` |
| Zweck | Langsamer EMA auf M15 zur Trendbestätigung |

### rsi_primary

| Feld | Wert |
|------|------|
| Tool | `calculate_indicator` |
| Output Key | `rsi_primary` |
| Indikator | `RSI` |
| Zeitrahmen | `SHORT_TF` (M15) |
| Periode | `4` |
| History | `3` |
| Zweck | Kurzperiodiger RSI für Momentum- und Timing-Signale |

Periode 4 (statt der üblichen 14) reagiert schneller, passend für M15-Handelsentscheidungen.

### atr_primary

| Feld | Wert |
|------|------|
| Tool | `calculate_indicator` |
| Output Key | `atr_primary` |
| Indikator | `ATR` |
| Zeitrahmen | `SHORT_TF` (M15) |
| Periode | `4` |
| History | `1` |
| Zweck | Aktueller ATR auf M15 zur Volatilitätsnormalisierung |

Wird als Nenner für S/R-Distanzberechnungen verwendet.

### h1_ema_fast

| Feld | Wert |
|------|------|
| Tool | `calculate_indicator` |
| Output Key | `h1_ema_fast` |
| Indikator | `EMA` |
| Zeitrahmen | `LONG_TF` (H1) |
| Periode | `3` |
| History | `3` |
| Zweck | Schneller EMA auf H1 für höheren Zeitrahmen Trendrichtung |

### h1_ema_slow

| Feld | Wert |
|------|------|
| Tool | `calculate_indicator` |
| Output Key | `h1_ema_slow` |
| Indikator | `EMA` |
| Zeitrahmen | `LONG_TF` (H1) |
| Periode | `8` |
| History | `3` |
| Zweck | Langsamer EMA auf H1 zur Trendbestätigung auf höherem Zeitrahmen |

### last_decision

| Feld | Wert |
|------|------|
| Tool | `get_last_decision` |
| Output Key | `last_decision` |
| Zweck | Vorheriges Analyseergebnis für Kontinuitätskontext |

### session_status

| Feld | Wert |
|------|------|
| Tool | `get_session_status` |
| Output Key | `session_status` |
| Zweck | Aktuelle Handelssessioninformationen |

### swing_levels_m15

| Feld | Wert |
|------|------|
| Tool | `get_swing_levels` |
| Output Key | `swing_levels_m15` |
| Zeitrahmen | `SHORT_TF` (M15) |
| Lookback | `100` |
| Max Levels | `10` |
| Zweck | Kurzfristige Swing-Hoch/Tief-Niveaus für Mikro-S/R-Berechnung |

### swing_levels_h1

| Feld | Wert |
|------|------|
| Tool | `get_swing_levels` |
| Output Key | `swing_levels_h1` |
| Zeitrahmen | `LONG_TF` (H1) |
| Lookback | `48` |
| Max Levels | `5` |
| Zweck | Höherer-Zeitrahmen-Swing-Niveaus für strukturelle S/R |

---

## Calculation Blocks

Calculation-Blöcke führen reines Python-Data-Processing durch. Sie haben keine externen Aufrufe — sie verbrauchen nur das, was Tool-Blöcke bereits abgerufen haben. Sie laufen sequentiell in Abhängigkeitsreihenfolge nach Abschluss aller Tool-Blöcke.

### Block hinzufügen

1. Typ aus dem „Add Calculation"-Dropdown wählen
2. „Add Calculation" klicken
3. Block ID setzen
4. Datenquellen verknüpfen (Dropdowns listen verfügbare Tool-Block-Output-Keys auf)
5. Typspezifische Parameter anpassen

### Block-Felder

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| **Block ID** | Text | Eindeutiger Bezeichner. Ergebnis in `calcs[block_id]` gespeichert. |
| **Enabled** | Checkbox | Wenn deaktiviert, wird Block übersprungen. |
| **Data Sources** | Dropdowns | Geben an welche Tool-Block-Outputs dieser Block verbraucht. |
| **Konfigurationsparameter** | Zahlenfelder | Typspezifische Einstellungen (Lookback-Perioden, Schwellenwerte). |
| **Script** (nur Script-Typ) | Code-Editor | Freies Python für benutzerdefinierte Berechnungen. |
| **Test** | Schaltfläche | Führt Block isoliert aus und zeigt Ergebnis-Dict oder Fehler. |
| **Remove** | Schaltfläche | Löscht diesen Block. |

### Verfügbare Calculation-Typen

| Typ | Zweck |
|-----|-------|
| `trend` | EMA-basierte Trendrichtung, Steigerung und Zustandsklassifikation |
| `rsi_state` | RSI-Niveau, Richtung, Timing-Signale und Konflikts-Flags |
| `m5_structure` | Kurzfristige Kerzenstruktur (Momentum, Range, Rejection) |
| `swing_sr_gate` | S/R-Näheprüfung mit Swing-Niveaus und ATR-Normalisierung |
| `close_quality` | Qualitätsbewertung jedes letzten Kerzen-Schlusses |
| `entry_gates` | Konsolidierte Boolean-Einstiegsbedingungsflaggen |
| `recent_context` | Rohe Kerzenlisten für LLM-Kontextbewusstsein |
| `script` | Freies Python mit Zugang zu allen Tool-Outputs und früheren Calc-Ergebnissen |

---

## Die Standard-aa_default_v1-Calculation-Blocks

### trend (primäre Kerzenquelle: m15_recent)

**Quellen**: `candles: m15_recent`, `ema_fast: ema_fast`, `ema_slow: ema_slow`

**Ausgabefelder**:
- `direction`: `long` / `short` / `neutral`
- `ema_fast_value`: aktueller Fast-EMA-Preis
- `ema_slow_value`: aktueller Slow-EMA-Preis
- `ema_fast_slope`: Fast-EMA-Steigerung (positiv = steigend)
- `ema_slow_slope`: Slow-EMA-Steigerung
- `price_vs_fast_ema`: `above` / `below` / `at`
- `price_vs_slow_ema`: `above` / `below` / `at`
- `trend_state`: `confirmed_bullish` / `confirmed_bearish` / `early_bullish_recovery` / `early_bearish_breakdown` / `neutral`

---

### rsi_state (primäre Kerzenquelle: m15_recent)

**Quellen**: `rsi: rsi_primary`

**Ausgabefelder**:
- `value`: aktueller RSI-Wert (0–100)
- `direction`: `rising` / `falling` / `flat`
- `level`: `extreme_oversold` / `oversold` / `neutral` / `overbought` / `extreme_overbought`
- `long_timing`: `good` / `neutral` / `poor`
- `short_timing`: `good` / `neutral` / `poor`
- `conflict_long`: `true` wenn RSI-Niveau mit Long-Signal in Konflikt steht
- `conflict_short`: `true` wenn RSI-Niveau mit Short-Signal in Konflikt steht

---

### m5_structure (primäre Kerzenquelle: m15_recent)

**Quellen**: `candles: m15_recent`, `atr: atr_primary`

Hinweis: Trotz des Namens `m5_structure` verwendet dieser Block M15-Kerzen. M15-Daten reduzieren das Rauschen in rohen M5-Kerzensequenzen.

**Ausgabefelder**:
- `structure`: `constructive_recovery` / `bearish_pressure` / `soft_rejection` / `range_bound`
- `range_bound`: Boolean
- `range_size_atr`: Bereichsgröße in ATR-Einheiten
- `largest_candle_body_atr`: größter Kerzenkörper in ATR-Einheiten
- `momentum_direction`: `bullish` / `bearish` / `neutral`

---

### micro_sr (primäre Kerzenquelle: m15_recent)

**Typ**: `swing_sr_gate`
**Quellen**: `candles: m15_recent`, `swing_levels: swing_levels_m15`, `atr: atr_primary`
**Parameter**: `sr_threshold: 0.5` (ATR-Einheiten)

Prüft die Nähe des aktuellen Preises zu nächsten Swing-abgeleiteten Unterstützungs- und Widerstandsniveaus auf M15.

**Ausgabefelder**:
- `nearest_resistance`: Preis des nächsten Widerstands über dem aktuellen Preis
- `nearest_support`: Preis der nächsten Unterstützung unter dem aktuellen Preis
- `distance_to_resistance_atr`: Distanz zum Widerstand in ATR-Einheiten
- `distance_to_support_atr`: Distanz zur Unterstützung in ATR-Einheiten
- `current_atr`: aktueller ATR-Wert für Normalisierung
- `sr_gate_passed_long`: `true` wenn Preis nicht zu nah am Widerstand für Long-Einstieg ist
- `sr_gate_passed_short`: `true` wenn Preis nicht zu nah an Unterstützung für Short-Einstieg ist

Der `sr_threshold` von 0,5 ATR bedeutet: Wenn der Preis innerhalb von 0,5× dem aktuellen ATR eines Widerstandsniveaus liegt, schlägt das Long-S/R-Gate fehl.

---

### structural_sr (primäre Kerzenquelle: h1_recent)

**Typ**: `swing_sr_gate`
**Quellen**: `candles: h1_recent`, `swing_levels: swing_levels_h1`, `atr: atr_primary`

Gleiche Logik wie micro_sr, aber mit H1-Kerzen und H1-Swing-Niveaus für strukturelle S/R-Analyse.

---

### h1_context (primäre Kerzenquelle: h1_recent)

**Typ**: `trend`
**Quellen**: `candles: h1_recent`, `ema_fast: h1_ema_fast`, `ema_slow: h1_ema_slow`

H1-Trendrichtung, identisch in der Struktur mit dem M15-`trend`-Block, aber auf H1-Daten operierend.

---

### close_quality (primäre Kerzenquelle: m15_recent)

**Quellen**: `candles: m15_recent`, `atr: atr_primary`

**Ausgabefelder**:
- `summary`: `strong_bullish` / `mild_bullish` / `neutral` / `mild_bearish` / `strong_bearish`
- `candles`: Array von Bewertungen pro Kerze

---

### entry_gates (keine einzelne primäre Quelle — gruppiert als `global`)

**Quellen**: `micro_sr`, `rsi: rsi_state`, `trend`, `m5_structure`, `h1_context: h1_context`

Konsolidiert alle Einzelsignale zu Boolean-Einstiegsflaggen für Long und Short.

**Ausgabefelder** (jedes ist ein Boolean):
- `long_sr_gate_passed`: micro_sr sagt Long-Einstieg ist nicht durch Widerstand blockiert
- `short_sr_gate_passed`: micro_sr sagt Short-Einstieg ist nicht durch Unterstützung blockiert
- `long_rsi_blocked`: RSI ist in einem Zustand der mit Long-Einstieg in Konflikt steht
- `short_rsi_blocked`: RSI steht mit Short-Einstieg in Konflikt
- `long_m5_confirmed`: m5_structure ist konstruktiv für Long
- `short_m5_confirmed`: m5_structure ist konstruktiv für Short
- `long_trend_aligned`: M15-Trendrichtung ist Long
- `short_trend_aligned`: M15-Trendrichtung ist Short
- `long_h1_aligned`: H1-Kontext unterstützt Long-Richtung
- `short_h1_aligned`: H1-Kontext unterstützt Short-Richtung

Diese Flaggen werden direkt in den LLM-Snapshot übergeben. Das LLM liest sie und gewichtet sie in seiner finalen Entscheidung, wird aber nicht mechanisch durch sie blockiert.

---

### recent_context (keine einzelne primäre Quelle — gruppiert als `global`)

**Quellen**: `candles_short: m15_recent`, `candles_long: h1_recent`

**Ausgabefelder**:
- `last_6_m15`: letzte 6 M15-Kerzen (OHLCV, kompaktes Format)
- `last_4_h1`: letzte 4 H1-Kerzen (OHLCV, kompaktes Format)

---

## Assembly Transform

Das Assembly-Transform ist ein Python-Skript, das nach Abschluss aller Tool-Blöcke und Calculation-Blöcke läuft. Sein Zweck ist die Kombination aller Ergebnisse zu einem finalen Snapshot-Dictionary.

Das Skript hat Zugang zu:
- `tool_outputs`: Dict das Output-Keys auf transformierte Tool-Ergebnisse mappt
- `calcs`: Dict das Block-IDs auf Calculation-Ergebnisse mappt, nach primärer Kerzenquelle gruppiert

### Gruppierung in `calcs`

Calculation-Blöcke sind nach ihrer primären Kerzenquelle gruppiert:
- `calcs["m15_recent"]`: Blöcke mit primärer Kerzenquelle `m15_recent` (trend, rsi_state, m5_structure, micro_sr, close_quality)
- `calcs["h1_recent"]`: Blöcke mit primärer Kerzenquelle `h1_recent` (structural_sr, h1_context)
- `calcs["global"]`: Blöcke ohne einzelne Kerzenquelle (entry_gates, recent_context)

### Minimales Assembly-Beispiel

```python
snapshot = {
    "trend": calcs["m15_recent"]["trend"],
    "rsi": calcs["m15_recent"]["rsi_state"],
    "structure": calcs["m15_recent"]["m5_structure"],
    "micro_sr": calcs["m15_recent"]["micro_sr"],
    "structural_sr": calcs["h1_recent"]["structural_sr"],
    "h1_direction": calcs["h1_recent"]["h1_context"],
    "entry_gates": calcs["global"]["entry_gates"],
    "recent_candles": calcs["global"]["recent_context"],
    "close_quality": calcs["m15_recent"]["close_quality"],
    "session": tool_outputs["session_status"],
    "last_decision": tool_outputs["last_decision"],
}
result = snapshot
```

Assembly Transform leer lassen, um das automatisch zusammengestellte Objekt zu verwenden, das alle Calculation-Ergebnisse und Tool-Outputs mit ihren Standard-Keys enthält.

---

## Aktionsschaltflächen

| Schaltfläche | Farbe | Funktion |
|--------------|-------|---------|
| **Update** | Grün | Änderungen am aktuell gewählten Profil speichern. Deaktiviert wenn kein Profil gewählt oder Validierungsfehler vorhanden. |
| **Save As New** | Blau | Aktuellen Stand als neues Profil speichern. |
| **Delete** | Rot | Aktuelles Profil löschen. Erfordert Bestätigung. |

---

## Live-Vorschau und Validierung

Die Sidebar zeigt den Echtzeit-Status des aktuellen Profils.

**Live-Vorschau** enthält:
- Profilname und Aggressivitätseinstellung
- Short/Long-Zeitrahmen-Werte
- Anzahl aktivierter vs. gesamt Tool-Blöcke
- Anzahl aktivierter vs. gesamt Calculation-Blöcke
- Assembly-Transform-Status (leer / angepasst)

**Validierung** listet alle Probleme auf, die das Speichern verhindern würden:
- Fehlende Block-IDs
- Doppelte Block-IDs innerhalb des Profils
- Tool-Blöcke ohne ausgewähltes Tool
- Calculation-Blöcke mit fehlenden Pflichtdatenquellen
- Leerer Profilname

---

## Execute-Vorschau

Klick auf **Execute** führt die vollständige Pipeline live aus:

1. Alle Tool-Blöcke werden gegen echte Daten für das Paar/Broker des gewählten Agenten ausgeführt
2. Alle Calculation-Blöcke laufen gegen die abgerufenen Daten
3. Das Assembly-Transform läuft
4. Ergebnisse werden in einem Dialog mit drei Bereichen angezeigt:

**Snapshot JSON**: Das vollständige Dictionary, das in den LLM-Prompt injiziert würde. Zum Überprüfen von Datenform, Wertebereichen und ob alle erwarteten Keys vorhanden sind.

**Decision Input**: Der finale Text, der in die LLM-Benutzernachricht einfließt — Prefix + serialisiertes JSON.

**Block Log**: Pro-Block-Ausführungszeit, Output-Zusammenfassung und eventuelle Warnungen oder Fehler.

Execute vor dem Zuweisen eines neuen oder geänderten Profils an einen Live-Agenten verwenden. Es erkennt Datenverfügbarkeitsprobleme, Transform-Skript-Fehler und unerwartete Ausgabeformen bevor sie den Live-Handel beeinflussen.

---

## Details zu Calculation Blocks

### ATR-Normalisierung verstehen

Mehrere Calculation-Blöcke drücken Distanzen und Größen in ATR (Average True Range)-Einheiten statt in absoluten Preiswerten aus:

- EURUSD ATR könnte 0,0008 sein; GBPJPY ATR könnte 0,45 sein
- Eine Distanz von „0,6 ATR" bedeutet dieselbe relative Nähe unabhängig vom Paar
- Der `sr_threshold` von 0,5 ATR für S/R-Gate-Prüfungen funktioniert für jedes Paar ohne manuelle Anpassung

### Trend-Zustand-Interpretation

| Zustand | Bedingung |
|---------|-----------|
| `confirmed_bullish` | Fast EMA > Slow EMA, beide steigend, Preis über beiden |
| `confirmed_bearish` | Fast EMA < Slow EMA, beide fallend, Preis unter beiden |
| `early_bullish_recovery` | Fast kreuzt über Slow, noch nicht bestätigt |
| `early_bearish_breakdown` | Fast kreuzt unter Slow, noch nicht bestätigt |
| `neutral` | EMAs flach oder choppy, Preis zwischen EMAs |

### RSI-Timing-Logik

- `long_timing = good`: RSI ist überverkauft (30–45) UND steigend — klassisches Überverkauft-Bounce-Signal
- `long_timing = neutral`: RSI-Neutralzone, weder bestätigend noch verneinend
- `long_timing = poor`: RSI überkauft, Long-Einstieg hat Momentum dagegen

---

## Snapshot-Probleme beheben

### Problem: Execute zeigt leer oder None für einen Tool-Block

- Prüfen ob Tool-Block aktiviert ist
- Tool-Argumente auf Gültigkeit prüfen (korrekter Zeitrahmen, Anzahl > 0)
- Prüfen ob Execute Context Agent auf ein Paar/Broker gesetzt ist das Daten in der Datenbank hat
- Transform-Skript auf Fehler prüfen (Block über Test-Schaltfläche isoliert testen)

### Problem: Calculation-Block zeigt Fehler oder None

- Prüfen ob Datenquellen-Dropdowns auf tatsächlich vorhandene Output-Keys verweisen
- Prüfen ob referenzierter Tool-Block aktiviert ist
- Wenn Tool-Block None zurückgab (Daten nicht verfügbar), gibt auch Calculation-Block None zurück — zuerst upstream Tool-Block reparieren

### Problem: Snapshot-JSON enthält nicht erwartete Keys

- Assembly-Transform-Skript prüfen — enthält es alle gewünschten Keys?
- Wenn Assembly-Transform leer ist, prüfen ob Calculation-Blöcke korrekt benannt und aktiviert sind

### Problem: LLM-Entscheidungen scheinen bestimmte Signale zu ignorieren

- Decision Input Prefix prüfen — weist er das LLM an, allen Feldern Aufmerksamkeit zu schenken?
- Tatsächliches Snapshot-JSON aus Execute mit dem Erwarteten vergleichen
- In Betracht ziehen, den Snapshot umzustrukturieren um die wichtigsten Signale auf oberster Ebene hervorzuheben

---

*Dieses Dokument behandelt Snapshot Config in OpenForexAI v0.7+. Für die Prompt-Konfiguration siehe [Decision Prompt](ui.config.decision_prompt.de.md). Für einen konzeptuellen Leitfaden siehe [Snapshot-Konfigurationsleitfaden](snapshot-config-guide.de.md).*
