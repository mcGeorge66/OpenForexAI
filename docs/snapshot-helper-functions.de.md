Snapshot-Helperfunktionen
==========================

Zweck
-----

`config/snapshot_helpers.py` ist die konfigurierbare Helper-Schicht für Snapshot-Transforms und Snapshot-Assembly.

Die Runtime importiert diese Datei, wenn sie vorhanden ist.

Fehlt die Datei, schlägt die Snapshot-Ausführung nicht allein deshalb fehl. Das bedeutet dann einfach, dass keine Helper-Funktionen aus dieser Datei in Snapshot-Skripten verfügbar sind.

Dadurch kannst du Snapshot-Helperlogik ändern, ohne die Haupt-Backend-Module anzufassen.

Dateipfad
---------

- `config/snapshot_helpers.py`

Wie sie verwendet wird
----------------------

Das Snapshot-System arbeitet in drei Ebenen:

1. `tool_blocks`
2. `transform_script` pro Tool-Block
3. `assembly_transform_script`

Die Helper-Datei unterstützt Ebene 2 und 3.

Typische Beispiele:

- Normalisierung von Candle-Tool-Output
- Normalisierung von Indicator-Tool-Output
- Richtungsbestimmung für Serien
- Aufbau wiederverwendbarer Payload-Blöcke für AA-Snapshots

Aktuelle Helper-Funktionen
--------------------------

### Micro-Helper

- `latest_value(values)`
  - gibt den letzten numerischen Wert einer Serie zurück

- `classify_series_direction(values, change_threshold=...)`
  - gibt `rising`, `flat` oder `falling` zurück

- `classify_indicator_direction(values, indicator_name)`
  - gibt indikatorspezifische Richtungslabels zurück
  - für ATR liefert die Funktion `expanding`, `contracting` oder `stable`

### Tool-Transform-Helper

- `normalize_candle_tool_output(tool_output, timeframe=None)`
  - wandelt rohe Candle-Zeilen in eine konsistente Candle-Struktur um

- `build_indicator_tool_output(tool_output, tool_input=None, all_outputs=None)`
  - Kompatibilitäts-Helper für Indicator-Transforms
  - ist nicht mehr der bevorzugte Standard
  - das Default-Indicator-Transform-Script verwendet jetzt direkt die Micro-Helper

### Assembly-Helper

- `build_base_payload(snapshot)`
- `build_h1_payload(snapshot, profile=None)`
- `build_m5_payload(snapshot, profile=None)`
- `build_support_resistance_payload(snapshot, profile=None)`
- `build_flags_payload(snapshot)`
- `build_entry_gates_payload(snapshot, profile=None)`
- `build_entry_blockers_payload(snapshot)`
- `include_entry_blockers(profile=None)`
- `include_tool_outputs(profile=None)`

Diese Helper sollen Assembly-Skripte kurz und lesbar halten.

Designregel
-----------

Helper-Funktionen sollten:

- klein bleiben
- genau eine klare Aufgabe haben
- JSON-serialisierbare Daten zurückgeben
- keine versteckten Seiteneffekte erzeugen

Wichtiger Hinweis
-----------------

Diese Helper sind Teil der Snapshot-Konfigurationsoberfläche.

Das bedeutet:

- Änderungen daran verändern das Snapshot-Verhalten
- wenn die Datei vorhanden ist, können Snapshot-Skripte ihre Helper-Funktionen verwenden
- fehlt die Datei, müssen Skripte ohne diese Helper-Funktionen auskommen
- referenziert ein Script einen nicht verfügbaren Helper-Namen, schlägt genau dieses Script fehl

Verwandte Dokumentation
-----------------------

- [Snapshot-Konfigurationshandbuch](snapshot-config-guide.de.md)
