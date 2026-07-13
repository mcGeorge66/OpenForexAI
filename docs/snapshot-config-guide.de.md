Snapshot-Konfigurationshandbuch
===============================

 
![ALT-TEXT](/image/Snapshot.jpg)

 

Was ein Snapshot ist
--------------------

Ein Snapshot ist ein vorbereitetes Runtime-Datenpaket für genau einen Agentenlauf.

Anstatt das LLM selbst Kerzen laden, Tools aufrufen und Indikatoren berechnen zu
lassen, baut die Runtime zuerst den Snapshot und gibt dann das fertige Ergebnis
an das LLM weiter.

Damit werden mehrere Ziele verfolgt:

-   geringere Token-Kosten

-   schnellere Antworten

-   weniger Tool-bezogene Fehler

-   konsistentere Entscheidungen

-   einfacheres Debugging

Einfach gesagt:

-   Tools sammeln und transformieren Daten

-   Calculation Blocks leiten aus den Tool-Outputs strukturierte Interpretationen ab

-   ein Assembly Transform fügt alles zur finalen Payload zusammen, die an das LLM gesendet wird

-   der Agent liest diesen vorbereiteten Snapshot und liefert sein Ergebnis

Ein Snapshot ist also der Markt-Kontext des Agenten für genau eine Entscheidung.

 

Wie der Snapshot-Ablauf funktioniert
------------------------------------

1.  Die Runtime wählt ein Snapshot-Profil aus.

2.  Die konfigurierten Tool-Blöcke laufen mit ihren konfigurierten Argumenten.
    Jeder Tool-Block kann optional ein eigenes Transform-Skript ausführen, das die rohe Ausgabe umformt,
    bevor sie gespeichert wird.

3.  Calculation Blocks laufen. Sie arbeiten auf den gespeicherten Tool-Outputs und
    erzeugen strukturierte Ergebnisse.

4.  Das Assembly-Transform-Skript fasst alles zur finalen Payload zusammen.

5.  Der Text aus `decision_input_prefix` wird vor den finalen Decision-Input gesetzt,
    und das Assembly-Ergebnis wird an das LLM geschickt.

Das bedeutet: Das Snapshot-Profil steuert sowohl

-   welche Daten gesammelt werden

-   wie diese Daten geformt und interpretiert werden, bevor sie das LLM erreichen

 

Überblick über den Snapshot-Config-Dialog
-----------------------------------------

Der Snapshot-Config-Dialog wird verwendet, um ein benanntes Snapshot-Profil zu
definieren.

Jedes Profil enthält diese Hauptbereiche, in der Reihenfolge des Datenflusses:

1. Basisinformationen (Name, Beschreibung)
2. Decision-Input-Prefix und Timeframe-Auswahl
3. Tool Blocks — welche Daten gesammelt und wie jeder Tool-Output transformiert wird
4. Calculation Blocks — wie Tool-Outputs in strukturierte Ergebnisse umgewandelt werden
5. Assembly Transform — wie alles zur finalen LLM-Payload zusammengefügt wird

Jeder Tool-Block hat zusätzlich eine `Test`-Aktion.

Dadurch öffnet sich ein Vorschau-Dialog mit:

-   der rohen Tool-Ausgabe

-   der transformierten Ausgabe nach dem Tool-Transform-Skript

-   den verwendeten Argumenten

-   dem Runtime-Kontext

-   möglichen Tool- oder Transform-Fehlern

Das ist der schnellste Weg, um zu prüfen, ob ein einzelner Tool-Block die richtige Zwischenstruktur liefert, bevor du die vollständige Snapshot-Vorschau ausführst.

Die Transformer-Skripte selbst sind separat hier dokumentiert:

- [Snapshot-Transformer-Handbuch](snapshot-transformers.de.md)

 

Basisfelder
-----------

### `Name`

Das ist der Profilname.

Er dient dazu, das Snapshot-Profil im System eindeutig zu identifizieren und
Agenten zuzuweisen.

Auswirkung:

-   Pflichtfeld beim Speichern

-   muss eindeutig sein

-   erscheint in Auswahllisten

Beispiele:

-   `aa_default_v1`

-   `eurusd_reversal_snapshot`

-   `mdac_profile_london_open`

### `Description`

Das ist eine lesbare Beschreibung, wofür das Profil gedacht ist.

Auswirkung:

-   ändert die Runtime-Logik nicht direkt

-   hilft dir und anderen, den Zweck des Profils zu verstehen

Gute Nutzung:

-   Strategie-Stil beschreiben

-   gewünschtes Pair oder Session benennen

-   Besonderheiten des Snapshots erläutern

 

---

`decision_input_prefix`
-----------------------

Das ist Freitext, der am Anfang des finalen Inputs steht, der an das LLM
gesendet wird.

Standard:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ text
Runtime-prepared market decision snapshot.
Use the snapshot as the complete market context.
Return strict JSON only.
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Wirkung:

-   sagt dem LLM, wie es den Snapshot behandeln soll

-   dient als kurze Laufzeit-Anweisung vor dem JSON-Payload

-   kann helfen, Ausgabefehler und Verwirrung zu reduzieren

Was es nicht macht:

-   es lädt keine Daten

-   es berechnet nichts

-   es ersetzt nicht das eigentliche Decision-Prompt-Profil

Auswirkung:

-   stärkere Instruktionen können die Disziplin der Antwort verbessern

-   zu viel Text erhöht die Token-Kosten

-   unklare Formulierungen können die Entscheidungsqualität verschlechtern

Empfehlung:

-   kurz halten

-   operativ formulieren

-   keine langen Strategietexte hier wiederholen

 

---

Timeframe-Auswahl
-----------------

Unterhalb von `decision_input_prefix` befinden sich zwei Auswahlfelder:

- **Short timeframe** — schnelle Kerzenquelle (Standard: `M15`)
- **Long timeframe** — langsame Kerzenquelle (Standard: `H1`)

Gültige Werte: `M5`, `M15`, `M30`, `H1`, `H4`, `D1`

Auswirkung:

-   die gewählten Werte werden im Profil als `short_timeframe` und `long_timeframe` gespeichert

-   Tool-Blöcke können diese Werte über die Platzhalter `SHORT_TF` und `LONG_TF` im Feld `arguments.timeframe` referenzieren

-   zur Laufzeit ersetzt die Runtime `SHORT_TF` automatisch durch den `short_timeframe`-Wert des Profils und `LONG_TF` durch `long_timeframe`

Das ist der empfohlene Weg, um einen Candle-Block mit der Timeframe-Auswahl des Profils zu verknüpfen. Wenn du den Selektor an einer Stelle änderst, werden alle verknüpften Blöcke automatisch aktualisiert — kein manuelles Bearbeiten der einzelnen Blöcke nötig.

Nutze diese Auswahl, wenn deine Strategie z. B. M15 + H4 oder M30 + D1 kombiniert.

---

Tool Blocks
-----------

Der Bereich Tool Blocks definiert, welche Tools zum Bauen des Snapshots
verwendet werden.

Das ist der wichtigste technische Teil des Profils.

Jeder Block sagt der Runtime:

-   welches Tool laufen soll

-   mit welchen Argumenten es läuft

-   unter welchem Schlüssel das Ergebnis gespeichert wird

-   wie die rohe Ausgabe umgeformt werden soll (via Transform-Skript)

### Warum Snapshots dieselben Tools wie Agenten verwenden

Das Snapshot-System verwendet dieselbe gemeinsame Tool-Schnittstelle wie die
Agenten.

Das ist bewusst so gebaut.

Das bedeutet:

-   ein Tool muss nur einmal implementiert werden

-   dasselbe Tool kann direkt von einem Agenten verwendet werden

-   dasselbe Tool kann auch vom Snapshot-Builder verwendet werden

-   Berechnungen bleiben im ganzen System konsistent

### Wie ein Snapshot ein Tool verwendet

Wenn du einen Tool-Block zu einem Snapshot-Profil hinzufügst, macht die Runtime
Folgendes:

1.  Tool aus der gemeinsamen Tool-Registry laden.

2.  Statische Argumente aus dem Profil anwenden.

3.  Tool im aktuellen Broker-/Pair-Kontext ausführen.

4.  Das `transform_script` des Blocks auf die rohe Ausgabe anwenden (wenn gesetzt).

5.  Das transformierte Ergebnis unter `output_key` speichern — für Calculation Blocks und den Assembly Transform.

Dadurch kannst du ohne Codeänderung anpassen:

-   welches Tool verwendet wird

-   welche Argumente das Tool bekommt

-   wie die rohe Ausgabe umgeformt wird

-   unter welchem Output-Key das Ergebnis gespeichert wird

### Block-Felder

#### `id`

Interner Name des Blocks.

Auswirkung:

-   dient zur Identifikation

-   sollte innerhalb des Profils eindeutig sein

#### `tool_name`

Das registrierte Tool, das ausgeführt wird.

Beispiele:

-   `get_candles`

-   `calculate_indicator`

-   eigene zukünftige Analyse-Tools

#### `output_key`

Name, unter dem der transformierte Tool-Output gespeichert wird.

Auswirkung:

-   dieser Schlüssel wird von Calculation Blocks in ihrer `sources`-Konfiguration verwendet

-   dieser Schlüssel wird auch im Assembly Transform verwendet, um über `tool_outputs` auf das Ergebnis zuzugreifen

-   sollte aussagekräftig und innerhalb des Profils eindeutig sein

#### `enabled`

Wenn deaktiviert, wird dieser Block übersprungen.

Auswirkung:

-   nützlich zum Testen oder Vergleichen von Varianten

#### `arguments`

Statische Tool-Argumente, mit denen der Block ausgeführt wird.

Beispiele:

-   `timeframe`

-   `count`

-   `indicator`

-   `period`

-   `history`

Spezielle Platzhalterwerte für `timeframe`:

-   `SHORT_TF` — wird zur Laufzeit durch den `short_timeframe`-Wert des Profils ersetzt

-   `LONG_TF` — wird zur Laufzeit durch den `long_timeframe`-Wert des Profils ersetzt

Die Verwendung dieser Platzhalter ist der empfohlene Weg, um einen Candle-Block mit der Timeframe-Auswahl des Profils zu verknüpfen. Wenn du den Selektor änderst, werden alle verknüpften Blöcke automatisch aktualisiert.

#### `transform_script`

Ein Python-Skript, das direkt nach dem Tool-Aufruf läuft.

Es empfängt die rohe Tool-Ausgabe und kann sie umformen, bevor das Ergebnis gespeichert wird.

Wenn leer, wird die rohe Tool-Ausgabe unverändert übernommen.

Das Skript hat Zugriff auf:

-   `raw_output` — das rohe Ergebnis des Tools

-   `arguments` — die verwendeten Argumente des Tool-Aufrufs

-   `snapshot` — das aktuelle Snapshot-Objekt

Es muss `result` setzen, um die transformierte Ausgabe zu erzeugen.

### Beispielhafte Tool-Blöcke

Typischer Candle-Block mit Timeframe-Platzhalter:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ json
{
  "id": "m15_recent",
  "tool_name": "get_candles",
  "output_key": "m15_recent",
  "enabled": true,
  "arguments": {
    "timeframe": "SHORT_TF",
    "count": 20
  }
}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Typischer Indikator-Block:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ json
{
  "id": "rsi_primary",
  "tool_name": "calculate_indicator",
  "output_key": "rsi_primary",
  "enabled": true,
  "arguments": {
    "indicator": "RSI",
    "period": 7,
    "timeframe": "LONG_TF",
    "history": 3
  }
}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Typischer eigener Zusatz-Block:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ json
{
  "id": "mdac_signal",
  "tool_name": "mdac",
  "output_key": "mdac_signal",
  "enabled": true,
  "arguments": {
    "timeframe": "SHORT_TF",
    "lookback": 24
  }
}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

---

Calculation Blocks
------------------

Calculation Blocks laufen, nachdem alle Tool-Blöcke abgeschlossen sind.

Sie arbeiten auf den gespeicherten Tool-Outputs und erzeugen strukturierte, semantisch bedeutsame Ergebnisse. Hier findet die Marktinterpretation statt — Trend, Support/Resistance, Entry-Bereitschaft und ähnliche abgeleitete Logik.

Die Ergebnisse werden in `snapshot["calculations"]` gespeichert und stehen dem Assembly Transform zur Verfügung.

### Wie Calculation-Ergebnisse gespeichert werden

Der Speicherort eines Calculation-Ergebnisses hängt vom Block-Typ ab:

-   Blöcke, deren primäre Kerzenquelle ein `output_key` ist (z. B. `m15_recent`), werden unter `calcs["m15_recent"]` gespeichert.

-   `entry_gates`-, `recent_context`- und `script`-Blöcke werden immer unter `calcs["global"]` gespeichert.

Wenn du also zwei `trend`-Blöcke hast — einen, der `m15_recent` liest, und einen, der `h1_recent` liest — landen ihre Ergebnisse jeweils in `calcs["m15_recent"]` und `calcs["h1_recent"]`.

Innerhalb jeder Gruppe werden Ergebnisse durch die Block-`id` adressiert.

### Block-Felder

#### `id`

Interner Name des Blocks. Wird auch als Schlüssel verwendet, unter dem das Ergebnis innerhalb seiner Gruppe gespeichert wird.

#### `type`

Der Berechnungstyp. Siehe die unten aufgeführten Typen.

#### `enabled`

Wenn deaktiviert, wird der Block übersprungen.

#### `sources`

Optional. Bildet benannte Eingaben auf `output_key`-Werte von Tool-Blöcken ab.

Beispiel:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ json
{
  "candles": "m15_recent",
  "ema_fast": "ema_fast_primary",
  "ema_slow": "ema_slow_primary"
}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Die linken Schlüssel sind typspezifische Eingabenamen. Die rechten Werte sind die `output_key`-Werte der Tool-Blöcke.

#### `config`

Optional. Typspezifische Parameter. Siehe die einzelnen Typen weiter unten.

### Calculation-Block-Typen

#### `trend`

Erstellt eine strukturierte Trend-Interpretation aus EMA-Fast- und EMA-Slow-Quellen.

Typische Quellen:

-   `candles` — die Kerzenserie (wird für die Preisposition verwendet)

-   `ema_fast` — der Tool-Output der schnellen EMA

-   `ema_slow` — der Tool-Output der langsamen EMA

Typische Ausgabefelder:

-   EMA-Ausrichtung

-   EMA-Slope-Bias

-   Preispositions-Bias

-   kombinierter Trend-State

Ergebnis wird in `calcs["<candles_output_key>"]["<block_id>"]` gespeichert.

#### `micro_sr`

Erstellt Mikro-Support/Resistance-Level aus einer Kerzenquelle.

Diese Level werden für Entry-Timing verwendet — sie liegen nah am Preis und reagieren empfindlich auf die jüngste Marktstruktur.

Ergebnis wird in `calcs["<candles_output_key>"]["<block_id>"]` gespeichert.

#### `structural_sr`

Erstellt strukturelle Support/Resistance-Level aus einer Kerzenquelle.

Diese Level werden für die breitere Trade-Struktur verwendet — sie liegen weiter vom Preis entfernt und repräsentieren stärkere historische Zonen.

Typische Konfiguration:

-   `min_gap_atr` — minimaler ATR-basierter Abstand vom aktuellen Preis, damit ein Level als strukturell gilt

Ergebnis wird in `calcs["<candles_output_key>"]["<block_id>"]` gespeichert.

#### `close_quality`

Bewertet die jüngste Candle-Qualität aus einer Kerzenquelle.

Typische Ausgabefelder:

-   bullish closes

-   bearish closes

-   net direction

-   gesamte Body-Größe relativ zu ATR

-   größte Body-Größe relativ zu ATR

-   Qualitätslabel

Typische Konfiguration:

-   `recent_count` — wie viele jüngste Kerzen ausgewertet werden

-   `weak_threshold_atr` — ATR-Multiplikator, unterhalb dessen Bewegung als schwach gilt

-   `strong_threshold_atr` — ATR-Multiplikator, oberhalb dessen Bewegung als stark gilt

Ergebnis wird in `calcs["<candles_output_key>"]["<block_id>"]` gespeichert.

#### `entry_gates`

Erstellt richtungsgetrennte Entry-Bereitschafts-Flags für Long und Short.

Typische Ausgabefelder:

-   `sr_gate_passed`

-   `rsi_blocked`

-   `m5_confirmed`

Typische Konfiguration:

-   `long_confirmed_structures` — Liste von Kerzenstruktur-Labels, die als gültige Long-Bestätigung gelten

-   `short_confirmed_structures` — Liste von Kerzenstruktur-Labels, die als gültige Short-Bestätigung gelten

Ergebnis wird immer in `calcs["global"]["<block_id>"]` gespeichert.

#### `recent_context`

Speichert ein jüngstes Kerzenfenster für den Zugriff im Assembly Transform.

Nützlich, wenn du einen kompakten Kerzenausschnitt in der finalen Payload einschließen möchtest, ohne den gesamten Tool-Output weiterzugeben.

Typische Konfiguration:

-   `count` — wie viele jüngste Kerzen gespeichert werden

Ergebnis wird immer in `calcs["global"]["<block_id>"]` gespeichert.

#### `script`

Freies Python-Skript mit Zugriff auf alle Tool-Outputs. Erzeugt ein benutzerdefiniertes Ergebnis-Dict.

Das Skript hat Zugriff auf:

-   `tool_outputs` — Dict aller transformierten Tool-Block-Ausgaben, nach `output_key` indiziert

-   `snapshot` — das aktuelle Snapshot-Objekt

Das Skript muss `result` auf ein Dict setzen.

Beispiel:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
# tool_outputs enthält alle transformierten Tool-Block-Outputs (nach output_key indiziert)
candles = tool_outputs.get("m15_recent") or []
rsi = tool_outputs.get("rsi_primary") or {}
result = {
    "custom_flag": True,
    "rsi_latest": rsi.get("latest"),
}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Ergebnis wird immer in `calcs["global"]["<block_id>"]` gespeichert.

### Zugriff auf Calculation-Ergebnisse im Assembly Transform

Der Assembly Transform empfängt das vollständige `snapshot`-Dict. Der Zugriff auf Berechnungen erfolgt so:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
calcs = snapshot.get("calculations", {})

# Blöcke, deren Kerzenquelle-output_key "m15_recent" ist
m15 = calcs.get("m15_recent", {})

# entry_gates-, recent_context- und script-Blöcke
global_calcs = calcs.get("global", {})

result = {
    "symbol": snapshot.get("symbol"),
    "timestamp_utc": snapshot.get("timestamp_utc"),
    "price": snapshot.get("latest_price"),
    "trend": m15.get("trend"),
    "entry_gates": global_calcs.get("entry_gates"),
}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

---

Assembly Transform
------------------

Das Assembly-Transform-Skript läuft, nachdem alle Tool-Blöcke und Calculation Blocks abgeschlossen sind.

Es empfängt das vollständige `snapshot`-Dict und muss `result` auf die finale Payload setzen, die an das LLM gesendet wird.

Das Assembly-Ergebnis wird direkt an das LLM zurückgegeben — es wird kein zusätzlicher Metadaten-Wrapper hinzugefügt.

### `transform_script` (pro Tool-Block)

Ein Python-Skript, das direkt nach jedem einzelnen Tool-Aufruf läuft.

Es empfängt die rohe Tool-Ausgabe und kann sie umformen, bevor das Ergebnis gespeichert wird.

Wenn leer, wird die rohe Tool-Ausgabe unverändert übernommen.

### `assembly_transform_script`

Ein Python-Skript, das läuft, nachdem alle aktivierten Tool-Blöcke und Calculation Blocks abgeschlossen sind.

Es empfängt das vollständige `snapshot`-Dict und fasst alles zur finalen Payload zusammen.

Das Skript muss `result` auf ein Dict setzen. Dieses Dict empfängt das LLM.

Minimales Beispiel:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
result = {
    "symbol": snapshot.get("symbol"),
    "timestamp_utc": snapshot.get("timestamp_utc"),
    "price": snapshot.get("latest_price"),
}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Strukturiertes Markt-Payload-Beispiel:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
calcs = snapshot.get("calculations", {})
m15 = calcs.get("m15_recent", {})
h1 = calcs.get("h1_recent", {})
global_calcs = calcs.get("global", {})

result = {
    "symbol": snapshot.get("symbol"),
    "timestamp_utc": snapshot.get("timestamp_utc"),
    "price": snapshot.get("latest_price"),
    "trend": m15.get("trend"),
    "micro_sr": m15.get("micro_sr"),
    "structural_sr": h1.get("structural_sr"),
    "close_quality": m15.get("close_quality"),
    "entry_gates": global_calcs.get("entry_gates"),
    "recent_context": global_calcs.get("recent_context"),
}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

BA-Beispiel (nur Tool-Outputs, keine abgeleitete Logik):

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
result = {"tool_outputs": tool_outputs}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

### Den Agenten-Zyklus aus dem Assembly-Skript abbrechen

Das Assembly-Skript hat Zugriff auf eine Variable `cancel` (Standard `False`) und eine optionale Variable `cancel_reason` (Standard `""`).

Wenn das Skript `cancel = True` setzt, überspringt die Runtime den LLM-Aufruf für diesen Trigger-Zyklus vollständig. Es wird keine Analyse durchgeführt, kein Ergebnis gespeichert. Der Agent wartet einfach auf den nächsten Trigger.

Das ist nützlich, wenn der Snapshot feststellen kann, dass die aktuellen Bedingungen einen LLM-Aufruf sinnlos machen — zum Beispiel wenn keine Trading-Session aktiv ist oder eine Vorbedingungsprüfung fehlschlägt.

Verfügbare Variablen:

| Variable | Typ | Standard | Beschreibung |
|---|---|---|---|
| `cancel` | bool | `False` | Wenn `True`, wird der LLM-Aufruf übersprungen |
| `cancel_reason` | str | `""` | Optionaler Log-Eintrag, warum abgebrochen wird |

Beispiel — Zyklus überspringen, wenn keine Forex-Session aktiv ist:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ python
calcs = snapshot.get("calculations", {})
global_calcs = calcs.get("global", {})

session = tool_outputs.get("session_status") or {}
if not session.get("active_sessions"):
    cancel = True
    cancel_reason = "no active session"
    result = {}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Wichtig:

-   `cancel` wird nur aus dem `assembly_transform_script` ausgewertet, nicht aus den pro-Tool-`transform_script`-Skripten

-   der Agent protokolliert den Abbruch auf INFO-Level mit dem `cancel_reason`

-   das Setzen von `cancel = True` erzeugt keinen Fehler und keine Warnung — es ist normales operatives Filtern

---

Skript-Editor
-------------

Alle Skriptfelder in der Snapshot Config verwenden einen Monaco-basierten Code-Editor mit Python-Syntaxhervorhebung und einem dunklen Theme.

Das betrifft:

-   das `transform_script` jedes Tool-Blocks

-   das `assembly_transform_script`

-   den `script`-Typ-Calculation-Block

Der Editor stellt drei Steuerelemente bereit:

### Snippets-Schaltfläche

Öffnet ein Dropdown mit kontextspezifischen Code-Snippets.

Ein Snippet auswählen, um es an der aktuellen Cursor-Position einzufügen.

Alle Snippets sind in `config/ui_snippets.json5` gespeichert und können direkt bearbeitet werden, ohne Quellcode anzufassen.

### Kopieren-Schaltfläche

Kopiert den vollständigen Skript-Inhalt in die Zwischenablage.

### Erweitern-Schaltfläche

Öffnet das Skript in einem Vollbild-Overlay-Modal für komfortables Bearbeiten.

Das Modal verwendet denselben Monaco-Editor mit derselben Syntaxhervorhebung.

Wenn du fertig bist, drücke die Apply-Schaltfläche, um die Änderungen in das Feld zurückzuschreiben.

---

Praktische Grundregel
---------------------

Verwende das Profil nach diesem Modell:

- **Tool Blocks** definieren, was gemessen wird und wie jede rohe Ausgabe umgeformt wird.
- **Calculation Blocks** definieren, was die Tool-Outputs bedeuten — Trend, S/R-Level, Entry-Bereitschaft und andere abgeleitete Struktur.
- **Assembly Transform** definiert die genaue Payload-Form, die das LLM erhält.

Für einen BA- oder GA-Agenten:

-   nur die benötigten Tool-Blöcke konfigurieren

-   ein `assembly_transform_script` schreiben, das genau die benötigte Datenstruktur zurückgibt

-   Calculation Blocks minimal halten oder leer lassen, wenn keine abgeleitete Logik benötigt wird

Für einen AA-Agenten:

-   Candle- und Indikator-Tool-Blöcke mit geeigneten `SHORT_TF`/`LONG_TF`-Platzhaltern konfigurieren

-   Calculation Blocks für Trend, S/R, Close Quality und Entry Gates hinzufügen

-   einen Assembly Transform schreiben, der die finale strukturierte Payload aus `snapshot["calculations"]` zusammensetzt

Das ist das Kernmodell des Snapshot-Config-Systems.
