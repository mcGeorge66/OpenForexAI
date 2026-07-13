﻿Snapshot-Transformer-Handbuch
=============================

Zweck
-----

Dieses Dokument erklärt, wie Snapshot-Transformer-Skripte funktionieren.

Im Fokus stehen:

- per-Tool `transform_script`
- `assembly_transform_script`
- verfügbare Eingabevariablen
- wohin transformierte Daten geschrieben werden
- wie ein Tool auf Ausgaben früherer Tools zugreifen kann

Verwende diese Anleitung, wenn du Transformer-Skripte im Snapshot-Config-Dialog schreiben oder ändern willst.

Transformer-Ebenen
------------------

Die Snapshot-Pipeline hat zwei Skript-Ebenen:

1. Tool-Transformer
2. Assembly-Transformer

### Tool-Transformer

Ein Tool-Transformer läuft direkt nach genau einem Tool-Aufruf.

Er bekommt die rohe Ausgabe dieses Tools und kann sie umformen, bevor das Ergebnis für den weiteren Snapshot-Aufbau gespeichert wird.

### Assembly-Transformer

Der Assembly-Transformer läuft, nachdem alle aktivierten Tools fertig sind.

Er kann auf alle transformierten Tool-Ergebnisse zugreifen und daraus die finale Snapshot-Payload-Struktur zusammensetzen.

Tool-Transformer: verfügbare Variablen
--------------------------------------

In einem per-Tool `transform_script` stehen diese Variablen zur Verfügung.

### `tool_input`

Das ist das Argument-Objekt, mit dem der aktuelle Tool-Aufruf ausgeführt wurde.

Beispiel:

```python
{
    "indicator": "RSI",
    "period": 7,
    "timeframe": "H1",
    "history": 3,
}
```

### `tool_output`

Das ist die rohe Ausgabe des aktuellen Tools vor der Transformation.

Beispiele:

- Liste mit Candle-Zeilen
- Indicator-Resultatobjekt
- Account-Status-Objekt
- Positionsliste

### `all_outputs`

Hier stehen die bereits transformierten Ausgaben früherer Tool-Blöcke desselben Snapshot-Laufs.

Wichtig:

- enthalten sind nur Blöcke, die vorher schon gelaufen sind
- zukünftige Blöcke sind nicht enthalten
- die Reihenfolge der Tool-Blöcke ist daher wichtig, wenn ein Block von einem anderen abhängt

### `result`

Das ist die Ausgabvariable des aktuellen Skripts.

Alles, was du in `result` schreibst, wird die transformierte Ausgabe des aktuellen Tool-Blocks.

Diese transformierte Ausgabe wird danach:

- unter dem `output_key` des Blocks gespeichert
- für spätere Tool-Transforms über `all_outputs` verfügbar
- für den Assembly-Transformer über `tool_outputs` verfügbar

### `in_` und `out`

Das sind Komfortvariablen.

- `in_` startet als Kopie der rohen Tool-Ausgabe
- `out` startet als Kopie der rohen Tool-Ausgabe

Wenn du willst, kannst du damit arbeiten:

```python
out["latest"] = 1.23
result = out
```

### Optionale Helper-Funktionen

Wenn `config/snapshot_helpers.py` existiert, werden Helper-Funktionen aus dieser Datei in den Script-Kontext injiziert.

Beispiele:

- `latest_value(...)`
- `classify_series_direction(...)`
- `classify_indicator_direction(...)`
- `normalize_candle_tool_output(...)`

Wenn die Datei nicht existiert, sind diese Helper-Namen im Script nicht verfügbar.

Das bedeutet:

- Skripte können trotzdem laufen
- aber nur, wenn sie keine fehlenden Helper-Namen verwenden

Tool-Transformer: Ausgabe
-------------------------

Die Regel ist einfach:

- schreibe das finale transformierte Ergebnis in `result`

### Identitätstransform

```python
result = tool_output
```

### Kompakter Indicator-Transform

```python
result = dict(tool_output)
points = tool_output.get("values") or tool_output.get("value") or []
values = [float(item["value"]) for item in points if isinstance(item, dict) and item.get("value") is not None]
indicator_name = str(tool_output.get("indicator") or tool_input.get("indicator") or "").upper()
result["indicator"] = indicator_name or result.get("indicator")
result["latest"] = latest_value(values)
result["direction"] = classify_indicator_direction(values, indicator_name)
result["values"] = points
if "value" in result:
    del result["value"]
```

Was nach einem Tool-Transform passiert
--------------------------------------

Nachdem ein Tool-Transformer fertig ist:

1. die rohe Tool-Ausgabe bleibt intern erhalten
2. die transformierte Ausgabe wird unter dem `output_key` des Blocks gespeichert
3. diese transformierte Ausgabe ist für spätere Blöcke über `all_outputs` verfügbar
4. der Assembly-Transformer kann später über `tool_outputs` darauf zugreifen

Assembly-Transformer: verfügbare Variablen
------------------------------------------

Im `assembly_transform_script` stehen diese Variablen zur Verfügung.

### `tool_outputs`

Das ist das Dictionary aller transformierten Tool-Ausgaben.

Die Schlüssel sind normalerweise die `output_key`-Werte der Blöcke.

Beispiel:

```python
tool_outputs["m5_recent"]
tool_outputs["ema_fast"]
tool_outputs["account_status"]
```

Das bedeutet:

- wenn ein Tool-Block `output_key = "ema_fast"` hat, kann das Assembly-Script mit `tool_outputs.get("ema_fast")` darauf zugreifen
- wenn ein Tool-Block `output_key = "open_positions"` hat, kann das Assembly-Script mit `tool_outputs.get("open_positions")` darauf zugreifen

Typisches sicheres Zugriffsmuster:

```python
ema_fast = tool_outputs.get("ema_fast")
if isinstance(ema_fast, dict):
    latest_ema = ema_fast.get("latest")
```

Warum das wichtig ist:

- das Assembly-Script kann gezielt genau die Tool-Outputs ziehen, die es braucht
- es muss nicht blind den gesamten Snapshot durchsuchen
- verschiedene Agentenprofile können verschiedene Tool-Blöcke auf eine klare und vorhersagbare Weise kombinieren

### `raw_tool_outputs`

Das ist das Dictionary aller rohen Tool-Ausgaben vor der Transformation.

In den meisten Profilen sollte `tool_outputs` bevorzugt werden.

Der Zugriff funktioniert genauso:

```python
raw_ema = raw_tool_outputs.get("ema_fast")
```

`raw_tool_outputs` sollte nur verwendet werden, wenn:

- ausdrücklich die unveränderte Tool-Ausgabe gebraucht wird
- der per-Tool-Transform etwas entfernt hat, das du noch prüfen willst
- du ein Transform-Problem debuggen willst

### `snapshot`

Das ist das teilweise bereits aufgebaute Snapshot-Objekt, das die Runtime vor dem Assembly-Schritt erstellt.

Es kann bereits Bereiche enthalten wie:

- `market_data_valid`
- `validation_errors`
- `symbol`
- `timestamp_utc`
- `strategy_aggressiveness`
- `features`
- `flags`
- `derived_metrics`
- `recent_context`
- `tool_outputs`

### `profile`

Das ist die aktuelle Snapshot-Profilkonfiguration als Dictionary.

Verwende es, wenn die Assembly-Logik von Profileinstellungen abhängt.

Beispiel:

```python
payload_cfg = profile.get("decision_payload") or {}
if payload_cfg.get("include_tool_outputs"):
    result["tool_outputs"] = tool_outputs
```

### `agent_context`

Das ist der Runtime-Kontext des aktuellen Snapshot-Laufs.

Typische Felder:

- `agent_id`
- `broker_name`
- `pair`
- `strategy_aggressiveness`

### `result`

Das ist die Ausgabvariable des Assembly-Skripts.

Alles, was du in `result` schreibst, wird die zusammengesetzte Snapshot-Payload.

Assembly-Transformer: Ausgabe
-----------------------------

Der Assembly-Transformer sollte das finale Objekt in `result` schreiben.

### Wie `result` das LLM erreicht

Was mit `result` passiert, hängt von der Option `include_metadata` in der Decision-Payload-Konfiguration ab:

**`include_metadata: true` (Standard — AA-Stil)**

Der Metadaten-Kopf wird dem Assembly-Ergebnis vorangestellt:

```json
{
  "market_data_valid": true,
  "validation_errors": [],
  "symbol": "EURUSD",
  "timestamp_utc": "...",
  "strategy_aggressiveness": "BALANCED",
  "price": { "latest": 1.176, "spread": 0.0001 },
  ... assembled result merged in ...
}
```

Verwende diese Einstellung, wenn das LLM Runtime-Kontext benötigt, z. B. das aktuelle Symbol, den Gültigkeitsstatus und die Aggressivitätseinstellung.

**`include_metadata: false` (BA/GA-Stil)**

Nur das Assembly-Ergebnis wird zurückgegeben, ohne Kopf:

```json
{
  "account": { ... },
  "positions": [ ... ]
}
```

Verwende diese Einstellung, wenn das LLM nur die Tool-Daten benötigt und der Kopf stört.

### BA-Beispiel

```python
result = {"tool_outputs": tool_outputs}
```

Kombiniert mit `include_metadata: false` im Decision Payload gibt das dem LLM genau die rohen Tool-Outputs und nichts weiter.

### AA-Beispiel

```python
result = build_base_payload(snapshot)
h1 = build_h1_payload(snapshot, profile)
if h1:
    result["h1"] = h1
```

Kombiniert mit `include_metadata: true` (Standard) gibt das dem LLM den Metadaten-Kopf plus die zusammengesetzte Markt-Payload.

### Identitätsbeispiel

```python
result = {"tool_outputs": tool_outputs}
```

Das ist das einfachste sinnvolle Assembly-Skript. Es gruppiert alle transformierten Tool-Outputs unter einem Schlüssel, ohne weitere Umstrukturierung.

### Benutzerdefiniertes Kombinationsbeispiel

```python
result = {
    "account": tool_outputs.get("account_status") or {},
    "positions": tool_outputs.get("open_positions") or [],
}
```

Warum das nützlich ist:

- ein BA-Profil kann daraus einen kompakten Execution-Snapshot nur aus Account- und Positionsdaten bauen
- das LLM bekommt genau den vorbereiteten Execution-Kontext, den es braucht
- zusätzliche Broker-Lookup-Tools werden im BA-Entscheidungslauf nicht mehr benötigt

Beispiel: Gezielter Zugriff auf einen Tool-Block
------------------------------------------------

Angenommen, du hast diesen Tool-Block:

```json
{
  "id": "ema_fast",
  "tool_name": "calculate_indicator",
  "output_key": "ema_fast"
}
```

Dann kann das Assembly-Script so darauf zugreifen:

```python
ema_fast = tool_outputs.get("ema_fast")
```

Wenn die transformierte Ausgabe so aussieht:

```json
{
  "indicator": "EMA",
  "period": 20,
  "timeframe": "H1",
  "history": 3,
  "latest": 1.176497,
  "direction": "rising",
  "values": [
    {"timestamp": "2026-05-11T01:00:00Z", "value": 1.176452},
    {"timestamp": "2026-05-11T02:00:00Z", "value": 1.176473},
    {"timestamp": "2026-05-11T03:00:00Z", "value": 1.176497}
  ]
}
```

dann kannst du sie so verwenden:

```python
ema_fast = tool_outputs.get("ema_fast") or {}
latest_ema = ema_fast.get("latest")
ema_direction = ema_fast.get("direction")
```

Praktischer Nutzen:

- du musst nicht wissen, an welcher späteren Stelle im Snapshot dieser Block landet
- du greifst direkt über den konfigurierten `output_key` darauf zu
- dadurch bleibt die Assembly-Logik explizit und leicht wartbar

Beispiel: Mehrere Tool-Blöcke kombinieren
-----------------------------------------

Beispiel:

```python
account = tool_outputs.get("account_status") or {}
positions = tool_outputs.get("open_positions") or []
orderbook = tool_outputs.get("orderbook_summary") or {}

result = {
    "account": account,
    "positions": positions,
    "orderbook": orderbook,
}
```

Praktischer Nutzen:

- nützlich für BA-Snapshots
- nur die ausgewählten Runtime-Daten werden weitergegeben
- der finale LLM-Input bleibt kompakt und zweckgerichtet

Wichtige Designregel
--------------------

Verwende die zwei Ebenen mit klar getrennter Verantwortung:

- Tool-Transformer:
  ein Tool-Ergebnis lokal vorbereiten
- Assembly-Transformer:
  viele transformierte Tool-Ergebnisse zur finalen Struktur zusammenbauen

Praktische Leitlinien
---------------------

- halte jeden Tool-Transformer klein
- nutze `result = tool_output` nur dann, wenn wirklich keine Vorverarbeitung nötig ist
- bevorzuge `tool_outputs` statt `raw_tool_outputs` im Assembly-Schritt
- nutze `profile` für bedingtes Verhalten
- nutze `snapshot`, wenn du bereits abgeleitete Runtime-Bereiche wie `features` oder `flags` verwenden willst
- halte die finale Assembly explizit und lesbar

Verwandte Dokumentation
-----------------------

- [Snapshot-Konfigurationshandbuch](snapshot-config-guide.de.md)
- [Snapshot-Helperfunktionen](snapshot-helper-functions.de.md)
