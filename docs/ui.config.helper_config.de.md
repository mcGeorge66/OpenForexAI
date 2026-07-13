[Zurück zu Config](ui.config.de.md)

# Helper Config

`Helper Config` ist ein Python-Editor für die Datei `config/snapshot_helpers.py`. Diese Datei enthält optionale Hilfsfunktionen, die in Snapshot-Transform-Scripts und Assembly-Scripts aufgerufen werden können — wiederverwendbare Python-Logik, die nicht in jedem Transform-Block dupliziert werden muss.

## Referenzdokumente
- [Snapshot-Helferfunktionen](snapshot-helper-functions.de.md)
- [Snapshot-Transformers](snapshot-transformers.de.md)
- [Snapshot-Config-Leitfaden](snapshot-config-guide.de.md)

---

## Was ist snapshot_helpers.py?

`config/snapshot_helpers.py` ist die konfigurierbare Helferschicht für die Snapshot-Pipeline. Es ist eine einfache Python-Datei, die die Runtime beim Start automatisch importiert — sofern sie vorhanden ist.

Funktionen, die in dieser Datei definiert sind, stehen in allen Snapshot-Scripts ohne Import-Anweisung zur Verfügung. Sie werden vor der Ausführung des Scripts in den Ausführungskontext injiziert. Fehlt die Datei, läuft die Snapshot-Ausführung normal weiter — Scripts haben dann einfach keine Helfer aus dieser Datei und müssen eigenständig sein.

Diese Trennung ermöglicht es, gemeinsame Snapshot-Logik zu ändern, ohne die Backend-Hauptmodule anfassen zu müssen. Alle Helferänderungen werden durch Bearbeiten und Speichern dieser Datei über den Helper-Config-Editor vorgenommen.

---

## Oberfläche

### Kopfleiste

| Element | Funktion |
|---|---|
| **Dateipfad** | Zeigt den vollständigen Pfad zur bearbeiteten Datei (`config/snapshot_helpers.py`) |
| **Jump to function…** | Dropdown mit allen `def`-Funktionen in der Datei, alphabetisch sortiert — Auswahl springt zur entsprechenden Zeile |
| **Refresh** | Lädt die aktuelle Version der Datei von der Disk, verwirft nicht gespeicherte Änderungen |
| **Save** | Führt Backend-Python-Syntaxcheck durch und schreibt die Datei wenn der Check bestanden wird |
| **Position** | Zeigt die aktuelle Cursor-Position als `Zeile:Spalte` |

### Jump to Function

Parsed automatisch alle Funktionsdefinitionen (`def name(`) aus dem aktuellen Editor-Inhalt und listet sie alphabetisch sortiert. Jeder Eintrag zeigt Funktionsname und Zeilennummer.

Nützlich wenn die Helpers-Datei groß wird — man kann sofort zu jeder Funktion navigieren ohne scrollen zu müssen.

### Zeilennummern

Links vom Editor angezeigt und scrollen synchron mit dem Text.

### Editor-Textarea

Vollständiger Python-Code-Editor. Unterstützt die gesamte Python-Syntax. Es gibt keine Autovervollständigung oder inline-Fehlerhervorhebung — der Syntaxcheck erfolgt nur beim Klick auf Save.

### Status-Meldungen

- **„Saved. Python syntax valid."** — Speichern erfolgreich, Syntax korrekt, Datei wurde geschrieben
- **Fehlermeldung mit Zeilenangabe** — Python-Syntaxfehler erkannt; die vorhandene Datei auf der Disk wurde nicht verändert. Die Fehlermeldung zeigt die Zeile, an der das Problem gefunden wurde.

---

## Verhalten beim Speichern

1. Wenn **Save** geklickt wird, wird der Code an das Backend zur Syntaxprüfung gesendet.
2. Bei Syntaxfehler: Fehlermeldung mit Zeilenangabe wird angezeigt. Die vorhandene Datei auf der Disk bleibt unverändert.
3. Bei fehlerfreier Syntax: Datei wird geschrieben und neue Helfer stehen für alle nachfolgenden Snapshot-Ausführungen zur Verfügung.

Der Syntaxcheck verhindert, dass fehlerhafter Code eingespielt wird und alle Snapshot-Läufe blockiert. Ein stiller Fehler beim Speichern würde jeden Agenten-Analysezyklus brechen — der Check ist eine Sicherheitsabsicherung.

Hinweis: Der Syntaxcheck erkennt Python-Parse-Fehler (ungültige Syntax, Einrückungsfehler, undefinierte Namen in Funktionssignaturen). Er garantiert nicht, dass die Logik korrekt ist oder die Funktionen wie beabsichtigt funktionieren. Nach dem Speichern immer testen.

---

## Wie Hilfsfunktionen in Scripts verwendet werden

Funktionen aus `snapshot_helpers.py` stehen automatisch in allen Transform-Scripts der Snapshot Config zur Verfügung. Sie müssen nicht importiert werden — sie werden vor Ausführung des Scripts in den Ausführungskontext injiziert.

### In einem Tool-Block Transform-Script

```python
# snapshot_helpers.py enthält: def normalize_candle_tool_output(output, timeframe=None): ...

# In einem tool block transform_script:
result = normalize_candle_tool_output(raw_output, timeframe="H1")
```

### In einem Assembly Transform-Script

```python
# snapshot_helpers.py enthält: def build_base_payload(snapshot): ...

# Im Assembly-Script:
base = build_base_payload(snapshot)
output = base | {"extra_field": some_value}
```

### In einem Calculation-Block-Script

In dieser Datei definierte benutzerdefinierte Helfer stehen auch in Calculation-Block-Scripts zur Verfügung, die Zwischenergebnisse verarbeiten.

---

## Eingebaute Hilfsfunktionen

Die folgenden Helfer sind Teil der Standard-`snapshot_helpers.py`, die mit OpenForexAI ausgeliefert wird. Sie decken die häufigsten Snapshot-Verarbeitungsmuster ab:

### Micro Helpers

**`latest_value(values)`**
Gibt den letzten numerischen (nicht-None) Wert aus einer Serie (Liste) zurück.

```python
last_close = latest_value(candle_closes)
```

**`classify_series_direction(values, change_threshold=...)`**
Analysiert die Richtung einer numerischen Serie und gibt `"rising"`, `"falling"` oder `"flat"` zurück.

```python
direction = classify_series_direction(ema_values)
```

**`classify_indicator_direction(values, indicator_name)`**
Gibt indikatorbezogene Richtungslabels zurück. Für ATR gibt es `"expanding"`, `"contracting"` oder `"stable"` zurück. Für andere Indikatoren fällt es auf `classify_series_direction`-Verhalten zurück.

```python
atr_state = classify_indicator_direction(atr_values, "ATR")
# gibt "expanding", "contracting" oder "stable" zurück
```

### Tool-Transform-Helfer

**`normalize_candle_tool_output(tool_output, timeframe=None)`**
Konvertiert rohe Kerzenzeilen aus Tool-Ausgabe in ein konsistentes, strukturiertes Kerzenformat. In Tool-Block-Transform-Scripts für Kerzen-Daten-Tools verwenden.

```python
candles = normalize_candle_tool_output(raw_output, timeframe="H1")
```

**`build_indicator_tool_output(tool_output, tool_input=None, all_outputs=None)`**
Kompatibilitätshelfer für Indikator-Transforms. Verarbeitet rohe Indikator-Tool-Ausgabe in ein strukturiertes Format. Hinweis: Der bevorzugte Ansatz für neue Scripts ist die direkte Verwendung der Micro Helpers.

### Assembly-Helfer

Diese Helfer sollen Assembly-Scripts kurz und lesbar halten, indem sie gängige Payload-Erstellungsmuster kapseln:

**`build_base_payload(snapshot)`**
Erstellt das Basis-Payload-Dict aus dem Snapshot-Objekt. Immer der Ausgangspunkt eines Assembly-Scripts.

**`build_h1_payload(snapshot, profile=None)`**
Erstellt den H1-Zeitrahmen-Abschnitt des Payloads.

**`build_m5_payload(snapshot, profile=None)`**
Erstellt den M5-Zeitrahmen-Abschnitt des Payloads.

**`build_support_resistance_payload(snapshot, profile=None)`**
Erstellt den Support/Resistance-Levels-Abschnitt.

**`build_flags_payload(snapshot)`**
Erstellt den Flags-Abschnitt (Entry Gates, Blocker und boolesche Bedingungen).

**`build_entry_gates_payload(snapshot, profile=None)`**
Erstellt speziell den Entry-Gates-Unterabschnitt.

**`build_entry_blockers_payload(snapshot)`**
Erstellt den Entry-Blockers-Unterabschnitt.

**`include_entry_blockers(profile=None)`**
Gibt einen Boolean zurück, ob Entry Blocker für das angegebene Profil eingeschlossen werden sollen.

**`include_tool_outputs(profile=None)`**
Gibt einen Boolean zurück, ob rohe Tool-Ausgaben für das angegebene Profil eingeschlossen werden sollen.

---

## Eigene Hilfsfunktionen schreiben

Die `snapshot_helpers.py` kann um eigene Funktionen erweitert werden. Sie werden sofort ohne weitere Konfiguration in allen Snapshot-Scripts verfügbar.

### Gestaltungsregeln

Gute Hilfsfunktionen sollten:

- Genau eine klar definierte Aufgabe erfüllen
- Explizite Argumente akzeptieren (keine versteckten Abhängigkeiten vom globalen Zustand)
- JSON-serialisierbare Daten zurückgeben (dict, list, string, number, bool, None)
- Keine versteckten Nebeneffekte haben
- Klein bleiben — große Funktionen in kleinere, kombinierbare aufteilen

### Beispiel: Pip-Formatierung

```python
def format_pips(price_diff, pip_size=0.0001):
    """Preisdifferenz in Pips umrechnen, auf 1 Dezimalstelle gerundet."""
    if price_diff is None:
        return None
    return round(price_diff / pip_size, 1)
```

Verwendung in einem Transform-Script:
```python
sl_pips = format_pips(entry_price - stop_loss_price)
```

### Beispiel: Trendklassifikation aus zwei EMAs

```python
def classify_trend(ema_fast, ema_slow, threshold=0.001):
    """
    'BULLISH', 'BEARISH' oder 'NEUTRAL' basierend auf EMA-Verhältnis zurückgeben.
    threshold: relative Separation, die für Trendklassifikation nötig ist.
    """
    if ema_fast is None or ema_slow is None:
        return "UNKNOWN"
    ratio = (ema_fast - ema_slow) / ema_slow
    if ratio > threshold:
        return "BULLISH"
    elif ratio < -threshold:
        return "BEARISH"
    return "NEUTRAL"
```

Verwendung:
```python
trend = classify_trend(ema_20_last, ema_50_last)
```

### Beispiel: Kerzen-Body-Analyse

```python
def candle_body_pct(open_price, close_price, high_price, low_price):
    """
    Body-Größe als Prozentsatz der gesamten Kerzen-Range zurückgeben.
    Gibt 0.0 zurück wenn die Kerzen-Range null ist (Doji).
    """
    candle_range = high_price - low_price
    if candle_range == 0:
        return 0.0
    body = abs(close_price - open_price)
    return round(body / candle_range * 100, 1)
```

### Beispiel: Preis-Position in einer Range

```python
def price_position_in_range(price, range_low, range_high):
    """
    Wo liegt der Preis innerhalb einer Range als Prozentsatz (0=unten, 100=oben).
    Gibt None zurück wenn Range null ist oder Eingaben fehlen.
    """
    if None in (price, range_low, range_high):
        return None
    total = range_high - range_low
    if total == 0:
        return None
    return round((price - range_low) / total * 100, 1)
```

### Beispiel: Session-Klassifikator

```python
def classify_forex_session(hour_utc):
    """
    Primäre Forex-Handelssession für eine gegebene UTC-Stunde zurückgeben.
    Gibt 'SYDNEY_TOKYO', 'TOKYO_LONDON_OVERLAP', 'LONDON',
    'OVERLAP_LDN_NY' oder 'NEWYORK' zurück.
    """
    if 22 <= hour_utc or hour_utc < 7:
        return "SYDNEY_TOKYO"
    elif 7 <= hour_utc < 8:
        return "TOKYO_LONDON_OVERLAP"
    elif 8 <= hour_utc < 13:
        return "LONDON"
    elif 13 <= hour_utc < 17:
        return "OVERLAP_LDN_NY"
    elif 17 <= hour_utc < 22:
        return "NEWYORK"
    return "OFF_HOURS"
```

---

## Wichtiger Hinweis zu Helferänderungen

Helfer sind Teil der Snapshot-Konfigurationsoberfläche. Das Ändern einer Hilfsfunktion ändert das Snapshot-Verhalten für jeden Agenten, der Scripts verwendet, die diese Funktion aufrufen.

- Verweist ein Script auf einen Helfernamen, der in der Datei nicht definiert ist (oder die Datei fehlt), schlägt das Script fehl und der Snapshot-Lauf schlägt fehl.
- Hat eine Hilfsfunktion einen Bug, der zur Laufzeit eine Exception wirft, schlägt jedes Transform- oder Assembly-Script fehl, das sie aufruft.
- Nach dem Speichern immer testen: im Test-Snapshot-Panel (zugänglich aus Decision Prompt) oder über den Tool Executor einen Snapshot ausführen.

---

## Typischer Ablauf

1. **Refresh** klicken, um sicherzustellen, dass die aktuelle Version der Datei vorliegt
2. **Jump to function** nutzen, um eine vorhandene Funktion zu finden, die geändert werden soll, oder ans Ende scrollen um eine neue hinzuzufügen
3. Code bearbeiten oder neue Funktion hinzufügen
4. **Save** klicken
5. Wenn ein Syntaxfehler angezeigt wird: Fehlermeldung lesen, angegebene Zeile korrigieren, erneut Save klicken
6. Nach erfolgreichem Speichern den betroffenen Snapshot im Decision-Prompt-Testpanel oder Tool Executor testen, um die korrekte Funktion der geänderten Funktion zu bestätigen
7. Liefert der Snapshot unerwartete Ausgaben, **Jump to function** nutzen um die geänderte Funktion schnell aufzurufen

---

## Siehe auch

- [Snapshot-Helferfunktionen](snapshot-helper-functions.de.md) — Referenz aller eingebauten Hilfsfunktionen
- [Snapshot-Transformers](snapshot-transformers.de.md) — Wie Transform-Scripts Helfer verwenden
- [Snapshot Config](ui.config.snapshot_config.de.md) — Snapshot-Profilstruktur und Calculation Blocks
- [Snapshot-Config-Leitfaden](snapshot-config-guide.de.md) — End-to-End-Leitfaden für den Aufbau von Snapshot-Profilen
