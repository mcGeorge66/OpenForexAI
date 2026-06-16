[Zurück zu Test](ui.test.de.md)

# Tool Executor

`Tool Executor` ruft ein einzelnes Tool direkt auf und zeigt das Ergebnis. Kein Agentenzyklus, kein LLM, kein Routing — nur der direkte Tool-Aufruf mit kontrollierten Eingaben. Ideal zum Testen von Tool-Parametern und zum Debuggen von unerwartetem Tool-Verhalten.

Einsatzbereiche:
- Prüfen ob ein Tool erreichbar ist und die erwarteten Daten liefert
- Parameter testen bevor sie in ein Snapshot-Profil eingebettet werden
- Tool-Ausgaben debuggen die in Agentenläufen unerwartet erscheinen

---

## Layout

Einspaltig scrollbar (auf großen Bildschirmen: Formular links, Ergebnis rechts).

---

## Kontext-Bereich (oben)

### Tool

Dropdown. **Pflichtfeld** — bestimmt welches Tool ausgeführt wird. Die Auswahl lädt das Tool-Schema und baut das Argumentformular dynamisch auf. Eine neue Auswahl setzt Formular und Ergebnis zurück.

### Agent

Dropdown. Optional. Bei Auswahl wird Broker, LLM und Pair automatisch aus der Agentenkonfiguration befüllt.

### Broker

Dropdown. Optional. Setzt den Broker-Kontext. Zeigt `Kurzname (Modulname)` zur Identifikation. Wird von Tools benötigt die auf Broker-Daten zugreifen (z. B. `place_order`, `get_account_summary`).

### LLM

Dropdown. Optional. Setzt den LLM-Kontext für Tools die ein LLM benötigen.

### Pair

Datalist-Eingabe. Optional. Währungspaar für den Kontext, z. B. `EURUSD`. Wird automatisch in Großbuchstaben umgewandelt. Schlägt bekannte Pairs aus den Agenten-Configs vor.

---

## Argumentformular

Wird dynamisch aus dem Tool-Schema aufgebaut. Jedes Tool hat seine eigenen Felder.

| Aspekt | Verhalten |
|---|---|
| **Feldtyp** | Text, Zahl oder Dropdown — abhängig vom Schema-Typ (`string`, `number`, `integer`, `boolean`, Enum) |
| **Pflichtfeld** | Mit `*` markiert; muss ausgefüllt sein |
| **Beschreibung** | Wird unter dem Feld angezeigt wenn im Schema vorhanden |
| **Leere Felder** | Werden nicht mit gesendet (keine Null-Übermittlung) |

### Input Schema (aufklappbar)

Zeigt das vollständige JSON-Schema des Tools zur Referenz.

### Quick Presets (nur bei Order-Tools)

Erscheint nur für `place_order` und `auto_place_order`. Vier Schaltflächen:

| Preset | Füllt vor |
|---|---|
| **Market** | Sofortiger Markt-Order |
| **Limit** | Limit-Order mit Limit-Preis |
| **Stop** | Stop-Order mit Stop-Preis |
| **Stop-Limit** | Stop-Limit-Order mit beiden Preisen |

### Validierung

Fehler werden als Amber-Liste oberhalb der Execute-Schaltfläche angezeigt. Häufige Regeln:

- Alle Pflichtfelder müssen ausgefüllt sein
- Bei Order-Tools: `units` (positive Ganzzahl), `lots` oder `risk_pct` muss vorhanden sein
- Bei `LIMIT`: `limit_price` Pflichtfeld
- Bei `STOP`: `stop_price` Pflichtfeld
- Bei `STOP_LIMIT`: beide Preise Pflichtfelder
- Bei `TRAILING_STOP`: `trailing_stop_distance` Pflichtfeld

Wenn alle Checks für ein Order-Tool bestanden sind, erscheint eine grüne Erfolgsmeldung.

### Execute

Führt das Tool mit den eingegebenen Argumenten aus. Deaktiviert wenn: kein Tool gewählt, Validierungsfehler vorhanden, Ausführung läuft.

---

## Ergebnisbereich

Zeigt das Tool-Ergebnis nach der Ausführung. Syntax-hervorgehobenes JSON:

| Farbe | Bedeutung |
|---|---|
| Hellblau | JSON-Schlüssel |
| Grün | Strings |
| Amber | Boolean-Werte |
| Lila | Zahlen |
| Grau | `null` |

Bei Fehler erscheint der Header in Rot mit der Fehlermeldung.

---

## Tool-Beschreibung

Zeigt die Beschreibung des gewählten Tools aus dem Schema. Bei Tools die eine Genehmigung erfordern, erscheint ein Warnzeichen: „⚠ This tool requires approval".

---

## Typischer Ablauf

1. **Tool** auswählen
2. Optional: **Agent** auswählen (füllt Kontext vor)
3. **Broker**, **LLM**, **Pair** bei Bedarf manuell setzen
4. Argumente ausfüllen (Pflichtfelder beachten)
5. Validierungsmeldungen prüfen
6. **Execute** klicken
7. Ergebnis-JSON prüfen

---

## Zweck und Anwendungsfälle im Detail

Der Tool Executor ist die Direkt-Zugriffs-Oberfläche für jedes im System registrierte Tool. Er umgeht das LLM vollständig — du gibst die Parameter an, klickst Execute, und das Tool läuft sofort gegen das Live-System. Das Ergebnis erscheint als formatiertes JSON.

**Wann Tool Executor vs. LLM Checker nutzen:**

| Szenario | Nutze |
|---|---|
| Rohe Tool-Ausgabe für exakte Parameter sehen | Tool Executor |
| Testen ob das LLM ein Tool korrekt aufruft | LLM Checker |
| Erkunden welche Parameter ein Tool akzeptiert | Tool Executor (automatisch generiertes Formular lesen) |
| Datenqualität prüfen (sind diese Kerzen korrekt?) | Tool Executor |
| System-Prompt-Verhalten testen | LLM Checker |
| Test-Order direkt aufgeben | Tool Executor |

Der Tool Executor ist besonders wertvoll für:

- **Snapshot-Profil-Debugging:** Vor dem Hinzufügen eines Tool-Calls zum Snapshot-Profil mit Tool Executor verifizieren dass die exakten Parameter das erwartete Datenformat liefern
- **Indikator-Validierung:** Bestätigen dass `calculate_indicator` mit einer bestimmten Indikator/Timeframe/Period-Kombination sinnvolle Werte liefert, bevor man sich in einem Agenten darauf verlässt
- **Order-Book-Inspektion:** Tatsächliche Order-Historie mit voller Filterkontrolle durchsuchen, inklusive `with_aa_analysis`-Flag für vollständige Analyst-Daten
- **Verbindungsprüfungen:** Bestätigen dass der Broker erreichbar ist und Daten liefert bevor Agenten-Zyklen gestartet werden

---

## Kontext-Bereich — Detaillierte Referenz

### Tool-Dropdown

Der primäre Selektor. Listet jedes registrierte Tool im System. Bei Auswahl eines Tools:
1. Wird das JSON-Schema des Tools vom Backend geladen
2. Wird das Argumentformular dynamisch mit passenden Feldtypen generiert
3. Wird jedes vorherige Ergebnis zurückgesetzt
4. Wird die Tool-Beschreibung im Tool-Description-Bereich angezeigt

### Agent-Dropdown

Optional. Bei Auswahl eines Agenten werden vorbelegt:
- **Broker** — aus dem Broker-Feld des Agenten
- **LLM** — aus dem LLM-Feld des Agenten
- **Pair** — aus dem Pair-Feld des Agenten

Broker, LLM und Pair können auch manuell gefüllt werden.

### Broker-Dropdown

Zeigt alle Broker-Module als `Kurzname (Modulname)`. Optional, aber erforderlich für broker-abhängige Tools wie `get_order_book`, `place_order`, `get_account_status`, `get_open_positions`, `close_position`, `modify_order`.

### LLM-Dropdown

Optional. Nur für Tools nötig, die ein LLM als Teil ihrer Ausführung aufrufen. Die meisten Marktdaten- und Trading-Tools benötigen das nicht.

### Pair-Eingabe

Datalist-Eingabe. Akzeptiert jeden Währungspaar-String (z.B. `EURUSD`, `USDJPY`). Automatisch in Großbuchstaben. Bietet Autocomplete-Vorschläge aus bekannten Agenten-Konfigurationen.

---

## Argumentformular — Detaillierte Referenz

Das Argumentformular wird dynamisch aus dem JSON-Schema des Tools generiert. Jeder Feldtyp, Platzhalter und jede Validierungsregel kommt direkt aus dem Schema.

### Feldtypen

**Text-Eingaben** (`string`-Typ im Schema):
- Für Freitext-String-Parameter wie `pair`, `price_source`, `comment`

**Zahlen-Eingaben** (`number` oder `integer`-Typ im Schema):
- Für numerische Parameter wie `count`, `period`, `lots`, `risk_pct`

**SELECT DROPDOWNS** (`enum`-Typ im Schema):
- Ersetzt Text-Eingaben für Felder mit fest definierten gültigen Werten
- Zeigt alle gültigen Optionen als Dropdown
- Beispiele:
  - `timeframe`: M1, M5, M15, M30, H1, H4, D1, W1, MN
  - `indicator`: RSI, ATR, SMA, EMA, BB, VWAP, DXY, SLOPE_E, SLOPE_S, MACD, CCI, STOCH, ADX
  - `sort_by`: nearest, prominent
  - `status_filter`: open, closed, all, rejected, cancelled, pending, partially_filled
  - `decision`: BUY, SELL, NEUTRAL
  - `order_type`: MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP

**BOOLEAN DROPDOWNS** (`boolean`-Typ im Schema):
- Zeigt ein SELECT mit zwei Optionen: `true` und `false`
- KEIN Text-Eingabefeld — verhindert Tippfehler und beseitigt Mehrdeutigkeit
- Beispiel: `with_aa_analysis`, `include_metadata`

### Pflichtfelder

Mit `*` nach dem Feldlabel markiert. Müssen ausgefüllt sein bevor Execute verfügbar ist.

### Feldbeschreibungen

Wenn das Tool-Schema eine `description` für eine Eigenschaft enthält, wird sie als Hilfstext unterhalb des Eingabefelds angezeigt.

### Leere Felder

Nicht ausgefüllte Felder werden NICHT an das Tool gesendet. Das Tool erhält nur die ausgefüllten Parameter. Optionale Parameter sind wirklich optional — leer lassen für Standard-Verhalten.

### Input Schema (aufklappbar)

Zeigt das vollständige rohe JSON-Schema für das Tool. Nützlich um:
- Die vollständige Liste akzeptierter Parameter zu verstehen
- Exakte Enum-Werte für Dropdowns zu sehen
- Detaillierte Beschreibungen für jeden Parameter zu lesen
- Pflicht- vs. optionale Parameter zu identifizieren

### Quick Presets (nur bei Order-Tools)

Erscheint nur für `place_order` und `auto_place_order`. Vier Preset-Schaltflächen:

| Preset | Füllt vor |
|---|---|
| **Market** | `order_type=MARKET` — sofortige Ausführung zum aktuellen Preis |
| **Limit** | `order_type=LIMIT`, aktiviert `limit_price` als Pflichtfeld |
| **Stop** | `order_type=STOP`, aktiviert `stop_price` als Pflichtfeld |
| **Stop-Limit** | `order_type=STOP_LIMIT`, beide Preis-Felder als Pflichtfelder |

### Validierungs-Panel

Amber-farbenes Panel oberhalb der Execute-Schaltfläche bei Validierungsproblemen. Listet alle Probleme:

- Pflichtfelder fehlen (nach Name aufgelistet)
- Bei Order-Tools: eines von `units`, `lots` oder `risk_pct` muss vorhanden sein
- Bei `LIMIT`-Orders: `limit_price` Pflichtfeld
- Bei `STOP`-Orders: `stop_price` Pflichtfeld
- Bei `STOP_LIMIT`-Orders: beide Preisfelder Pflicht
- Bei `TRAILING_STOP`-Orders: `trailing_stop_distance` Pflichtfeld

Bei bestandener Validierung erscheint eine grüne Erfolgsmeldung.

### Execute-Schaltfläche

Deaktiviert während: kein Tool gewählt, Pflichtfelder leer, Validierungsfehler vorhanden, vorherige Ausführung läuft noch.

---

## Ergebnisbereich — Detaillierte Referenz

Zeigt den Rückgabewert des Tools als syntax-hervorgehobenes JSON.

### Farbcodierung

| Farbe | JSON-Element |
|---|---|
| Hellblau | Objekt-Schlüssel / Eigenschaftsnamen |
| Grün | String-Werte |
| Amber/Gelb | Boolean-Werte (`true`, `false`) |
| Lila | Zahlen-Werte |
| Grau | `null`-Werte |

### Erfolgsantwort

Panel-Header zeigt grünes "Success"-Badge mit Ausführungszeit. JSON-Body zeigt den vollständigen Rückgabewert.

### Fehlerantwort

Panel-Header zeigt rotes "Error"-Badge mit Fehlermeldung. Häufige Fehler:
- "Broker not connected" — Broker-Adapter läuft nicht oder ist nicht erreichbar
- "Pair not found" — Pair nicht auf dem Broker verfügbar
- "Insufficient margin" — nicht genug Margin für das Order-Tool
- "Tool not found" — Tool-Name ungültig oder nicht registriert

### Kopieren-Schaltfläche

Obere rechte Ecke des Ergebnis-Panels. Kopiert das vollständige JSON-Output in die Zwischenablage. Nützlich für:
- Einfügen in den LLM Checker um zu testen wie ein Agent diese Daten interpretieren würde
- Daten-Probleme mit der tatsächlichen Ausgabe melden
- Erwartete Ausgaben für Vergleichstests speichern

---

## Vollständige Tool-Referenz mit Parametern

### get_candles

Ruft OHLCV-Kerzendaten für ein Währungspaar und Zeitrahmen ab.

| Parameter | Typ | Pflicht | Beschreibung |
|---|---|---|---|
| pair | string | Ja | Währungspaar, z.B. EURUSD |
| timeframe | enum Dropdown | Ja | M1, M5, M15, M30, H1, H4, D1, W1, MN |
| count | integer | Ja | Anzahl abzurufender Kerzen (1–500) |

**Beispielergebnis:** Array von Kerzen-Objekten: `[{"time": "2026-06-03T10:00:00", "open": 1.0921, "high": 1.0934, "low": 1.0918, "close": 1.0929, "volume": 1842}, ...]`

**Test-Tipp:** Mit kleiner Anzahl beginnen (5–10) um die korrekte Datenrückgabe zu prüfen.

---

### calculate_indicator

Berechnet einen technischen Indikator für ein Währungspaar und Zeitrahmen.

| Parameter | Typ | Pflicht | Beschreibung |
|---|---|---|---|
| indicator | enum Dropdown | Ja | RSI, ATR, SMA, EMA, BB, VWAP, DXY, SLOPE_E, SLOPE_S, MACD, CCI, STOCH, ADX |
| period | integer | Ja | Indikator-Periode (z.B. 14 für RSI, 20 für SMA) |
| timeframe | enum Dropdown | Ja | M1, M5, M15, M30, H1, H4, D1, W1, MN |
| history | integer | Nein | Anzahl historischer Werte (Standard: 1) |
| smooth_period | integer | Nein | Glättungsperiode für Indikatoren die es unterstützen (z.B. SLOPE_E, SLOPE_S) |
| pair | string | Nein | Währungspaar (Standard: Kontext-Pair) |

**Indikator-Hinweise:**
- `SLOPE_E` — Exponentieller Preis-Slope, nutzt smooth_period für EMA-Berechnung
- `SLOPE_S` — Einfacher Preis-Slope, nutzt smooth_period für SMA-Berechnung
- `BB` — Bollinger Bänder, gibt upper/middle/lower zurück
- `VWAP` — Volumengewichteter Durchschnittspreis
- `DXY` — US-Dollar-Index (wenn vom Datenanbieter verfügbar)

**Beispielergebnis für RSI:** `{"value": 58.3, "previous": 56.1, "timestamp": "2026-06-03T10:00:00"}`

**Beispielergebnis für BB:** `{"upper": 1.0945, "middle": 1.0921, "lower": 1.0897, "timestamp": "2026-06-03T10:00:00"}`

---

### get_swing_levels

Identifiziert Swing-Hochs und -Tiefs aus der Preishistorie.

| Parameter | Typ | Pflicht | Beschreibung |
|---|---|---|---|
| timeframe | enum Dropdown | Ja | M15, H1, H4, D1 |
| max_levels | integer | Nein | Maximale Anzahl zurückzugebender Level (Standard: 10) |
| lookback | integer | Nein | Anzahl zu analysierender Kerzen |
| atr_period | integer | Nein | ATR-Periode für Lücken-Filterung (Standard: 14) |
| min_gap_atr | number | Nein | Mindestabstand zwischen Leveln als ATR-Vielfaches (Standard: 0.5) |
| sort_by | enum Dropdown | Nein | nearest (nach Preisabstand), prominent (nach Bedeutung) |
| price_source | string | Nein | Welcher Preis: close, high_low (Standard) |

**Beispielergebnis:** `[{"level": 1.0880, "type": "support", "strength": 3, "distance_atr": 1.2, "last_touch": "2026-05-28"}, ...]`

**Test-Tipps:**
- `sort_by=nearest` für Level nahe am aktuellen Preis
- `sort_by=prominent` für historisch bedeutendste Level
- `lookback` erhöhen für ältere, übergeordnete Swing-Level
- `min_gap_atr` verringern für feinere Level, erhöhen für nur wichtige Level

---

### get_order_book

Ruft das Order-Buch (Handelshistorie) für den gewählten Broker ab.

| Parameter | Typ | Pflicht | Beschreibung |
|---|---|---|---|
| broker | string | Nein | Broker-Modul-Name |
| pair | string | Nein | Filter nach Pair (leer lassen für alle Pairs) |
| status_filter | enum Dropdown | Nein | open, closed, all, rejected, cancelled, pending, partially_filled |
| limit | integer | Nein | Maximale Anzahl zurückzugebender Orders |
| with_aa_analysis | boolean Dropdown | Nein | true = vollständige Analyst-Daten inkl. market_context_snapshot; false = saubere Ausgabe |

**Der `with_aa_analysis`-Parameter:**
- `false` (Standard): gibt saubere Order-Daten ohne großes Snapshot-JSON zurück
- `true`: gibt die vollständigen Analyst-Daten zurück einschließlich des kompletten `market_context_snapshot` der beim Aufgeben der Order aktiv war — nützlich um zu prüfen was der Agent "gesehen" hat als er die Handelsentscheidung traf

**`status_filter`-Werte erklärt:**
- `open`: aktuell offene Positionen
- `closed`: geschlossene Positionen
- `pending`: aufgegebene aber noch nicht ausgeführte Orders (z.B. Limit-Orders)
- `partially_filled`: teilweise ausgeführte Orders
- `rejected`: vom Broker abgelehnte Orders
- `cancelled`: vor Ausführung stornierte Orders
- `all`: alle Orders unabhängig vom Status

---

### get_account_status

Gibt aktuellen Kontostand, Equity, Margin und freie Margin zurück.

Keine Pflichtparameter (nutzt Kontext-Broker).

**Beispielergebnis:** `{"balance": 10500.00, "equity": 10487.50, "margin": 25.00, "margin_free": 10462.50, "margin_level_pct": 41950.0, "currency": "USD"}`

---

### get_open_positions

Gibt alle aktuell offenen Positionen zurück.

| Parameter | Typ | Pflicht | Beschreibung |
|---|---|---|---|
| broker | string | Nein | Broker-Modul-Name |
| pair | string | Nein | Filter nach Pair |

---

### get_session_status

Gibt aktuelle Handelssessions-Informationen zurück.

Keine Pflichtparameter.

**Beispielergebnis:** `{"current_time_utc": "2026-06-03T10:30:00", "active_sessions": ["london"], "next_session": "new_york", "next_session_open_utc": "2026-06-03T12:00:00"}`

---

### get_last_decision

Gibt die letzte Handelsentscheidung eines Agenten zurück.

| Parameter | Typ | Pflicht | Beschreibung |
|---|---|---|---|
| agent_id | string | Nein | Filter nach spezifischer Agent-ID |
| pair | string | Nein | Filter nach Pair |

---

### place_order

Gibt eine neue Handels-Order direkt auf.

| Parameter | Typ | Pflicht | Beschreibung |
|---|---|---|---|
| pair | string | Ja | Währungspaar |
| direction | enum Dropdown | Ja | BUY, SELL |
| order_type | enum Dropdown | Ja | MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP |
| units | integer | Nein* | Einheiten (eines von: units, lots oder risk_pct Pflicht) |
| lots | number | Nein* | Positionsgröße in Lots |
| risk_pct | number | Nein* | Risiko als Prozentsatz des Kontostands |
| limit_price | number | Nein | Pflicht für LIMIT und STOP_LIMIT |
| stop_price | number | Nein | Pflicht für STOP und STOP_LIMIT |
| stop_loss | number | Nein | Stop-Loss-Preis |
| take_profit | number | Nein | Take-Profit-Preis |
| trailing_stop_distance | number | Nein | Pflicht für TRAILING_STOP |
| comment | string | Nein | Order-Kommentar/Label |
| broker | string | Nein | Broker-Modul-Name |

**Warnung:** Dieses Tool gibt echte Orders beim gewählten Broker auf. Nur auf Demo-Konten beim Testen verwenden.

---

### auto_place_order

Gibt eine Order mit automatischer Parameterauflösung aus der letzten Agenten-Entscheidung auf.

| Parameter | Typ | Pflicht | Beschreibung |
|---|---|---|---|
| pair | string | Ja | Währungspaar |
| broker | string | Nein | Broker-Modul-Name |
| override_direction | enum Dropdown | Nein | Richtung aus der letzten Entscheidung überschreiben |
| override_risk_pct | number | Nein | Risikoprozentsatz überschreiben |

---

### close_position

Schließt eine offene Position.

| Parameter | Typ | Pflicht | Beschreibung |
|---|---|---|---|
| position_id | string | Ja | Zu schließende Positions-ID |
| broker | string | Nein | Broker-Modul-Name |
| units | integer | Nein | Teilschließung — zu schließende Einheiten (weglassen für vollständige Schließung) |

---

### modify_order

Modifiziert eine bestehende ausstehende oder offene Order.

| Parameter | Typ | Pflicht | Beschreibung |
|---|---|---|---|
| order_id | string | Ja | Zu modifizierende Order-ID |
| stop_loss | number | Nein | Neuer Stop-Loss-Preis |
| take_profit | number | Nein | Neuer Take-Profit-Preis |
| limit_price | number | Nein | Neuer Limit-Preis (für Limit-Orders) |
| broker | string | Nein | Broker-Modul-Name |

---

### raise_alarm

Löst ein Alarm-Ereignis auf dem Event-Bus aus.

| Parameter | Typ | Pflicht | Beschreibung |
|---|---|---|---|
| alarm_type | string | Ja | Typ/Kategorie des Alarms |
| message | string | Ja | Alarm-Nachrichtentext |
| severity | enum Dropdown | Nein | info, warning, critical |
| pair | string | Nein | Zugehöriges Pair falls relevant |

---

### trigger_sync

Löst ein Synchronisierungs-Ereignis aus um eine Datenaktualisierung zu erzwingen.

| Parameter | Typ | Pflicht | Beschreibung |
|---|---|---|---|
| sync_type | string | Nein | Was synchronisiert werden soll (z.B. "positions", "orders", "account") |
| broker | string | Nein | Zu synchronisierender Broker |

---

## Praktische Beispiele

### Beispiel 1: H1-RSI vor dem Hinzufügen zum Snapshot-Profil prüfen

Du möchtest H1-RSI (Periode 14) für EURUSD zu deinem Snapshot-Profil hinzufügen. Vor dem Hinzufügen prüfen ob korrekte Werte zurückgegeben werden.

1. `calculate_indicator` auswählen
2. Pair = EURUSD setzen (oder EURUSD-Agenten wählen)
3. Formular ausfüllen:
   - indicator = RSI (Dropdown)
   - period = 14
   - timeframe = H1 (Dropdown)
   - history = 3 (3 aufeinanderfolgende Werte zur Plausibilitätsprüfung)
4. Execute klicken
5. Prüfen: sind die zurückgegebenen RSI-Werte in einem sinnvollen Bereich (0–100)?

### Beispiel 2: Prüfen warum Swing-Level auf dem Chart falsch aussehen

Ein Agent referenziert H4-EURUSD-Swing-Level bei 1.0850 aber du siehst das Level nicht auf deinem Chart.

1. `get_swing_levels` auswählen
2. Pair = EURUSD setzen
3. Formular ausfüllen:
   - timeframe = H4 (Dropdown)
   - max_levels = 10
   - sort_by = prominent (Dropdown)
   - lookback = 200
4. Execute klicken
5. Zurückgegebene Level überprüfen — ist 1.0850 vorhanden?

### Beispiel 3: Order-Historie mit vollständigen Analyst-Daten inspizieren

Eine Trade-Entscheidung war falsch. Du möchtest den Marktkontext sehen der zum Zeitpunkt der Order aktiv war.

1. `get_order_book` auswählen
2. Relevanten Broker wählen
3. Formular ausfüllen:
   - pair = EURUSD
   - status_filter = closed (Dropdown)
   - limit = 10
   - with_aa_analysis = true (Boolean-Dropdown)
4. Execute klicken
5. Im Ergebnis-JSON die betreffende Order finden
6. `market_context_snapshot`-Feld aufklappen — zeigt den vollständigen Analyst-Snapshot der beim Aufgeben der Order aktiv war

**Hinweis:** `with_aa_analysis=true` gibt deutlich größere JSON-Objekte zurück. `false` für eine saubere Übersicht, `true` nur wenn das analytische Detail benötigt wird.

### Beispiel 4: Kontostand vor manuellem Test-Trade prüfen

1. `get_account_status` auswählen
2. Broker wählen
3. Execute klicken (keine weiteren Parameter nötig)
4. Prüfen: balance, margin_free — genug Margin für die geplante Test-Order?

### Beispiel 5: MARKET-Order auf Demo-Broker testen

1. Bestätigen dass der gewählte Broker das Demo-Konto ist
2. `place_order` auswählen
3. "Market"-Preset klicken für order_type=MARKET
4. Verbleibende Felder ausfüllen:
   - pair = EURUSD
   - direction = BUY (Dropdown)
   - risk_pct = 0.5
   - stop_loss = 1.0880
   - take_profit = 1.0980
   - comment = "ToolExecutor Test"
5. Prüfen: Validierungs-Panel zeigt grün
6. Execute klicken
7. Ergebnis prüfen: `order_id`, `status`, `fill_price`
8. Sofort `get_open_positions` ausführen um zu bestätigen dass die Position sichtbar ist

### Beispiel 6: Offene Position manuell schließen

1. Zuerst `get_open_positions` ausführen um die position_id zu erhalten
2. Position-ID notieren (z.B. "P12345")
3. `close_position` auswählen
4. Formular ausfüllen:
   - position_id = P12345
   - (units leer für vollständige Schließung)
5. Execute klicken
6. Ergebnis prüfen: status = "closed"
7. `get_open_positions` erneut ausführen um Entfernung zu bestätigen

---

## Tipps und Best Practices

- **Marktdaten-Tools immer verifizieren bevor sie in Snapshot-Profile übernommen werden** — Datenformat kann sich mit Broker-Adapter-Updates ändern
- **`status_filter` bei `get_order_book` nutzen** — "all" gibt viele Datensätze zurück; auf "open" oder "closed" filtern für gezielte Inspektion
- **Indikator-Werte mit Charting-Plattform vergleichen** — wenn Werte erheblich abweichen, Zeitrahmen und Periode exakt prüfen
- **Für Swing-Level-Tests mehrere `sort_by`- und `lookback`-Kombinationen ausprobieren**
- **Der Boolean-Dropdown für `with_aa_analysis` ist KEIN Textfeld** — aus Dropdown wählen, nicht "true" oder "false" eintippen
- **Ergebnisse regelmäßig kopieren** — das Ergebnis-Panel zeigt nur die letzte Ausführung; jedes Ergebnis kopieren bevor mit dem nächsten Test fortgefahren wird
- **Latenz prüfen** — die im Ergebnis-Header angezeigte Ausführungszeit zeigt wie lange das Tool benötigt; langsame Tools (>500ms) benötigen möglicherweise Optimierung in Snapshot-Profilen die sie mehrfach aufrufen
