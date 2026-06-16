[Zur Dokumentationsübersicht](README.de.md)

# openforexai/data — Marktdatenfluss

Dieses Paket verarbeitet Marktdatenspeicherung, Abruf, Resampling,
Indikatorberechnung und tool-seitigen Datenzugriff.

## Zentrale Dateien

| Datei | Zweck |
|---|---|
| `container.py` | Laufzeit-Datendrehscheibe |
| `resampler.py` | Baut höhere Timeframes aus M5 |
| `indicators.py` | Reine Indikatorberechnungen |
| `indicator_tools.py` | Tool-seitige Indikatorausführung |
| `correlation.py` | Korrelationsanalyse |
| `normalizer.py` | Hilfen zur Daten-Normalisierung |

## Kernprinzip

M5 bleibt der primär gespeicherte Timeframe.

Die Runtime speichert M5-Kerzen und leitet höhere Timeframes daraus ab, zum
Beispiel:

- `M15`
- `M30`
- `H1`
- `H4`
- `D1`

Dadurch bleibt die Datenerfassung konsistent und es werden keine separaten
Broker-Calls für jeden Timeframe benötigt.

## Aktueller Event-Fluss

Die Live-Runtime arbeitet heute mit einer M5-Update-Pipeline, die
Datenaktualisierung und Agent-Trigger voneinander trennt.

Wichtige Event-Konzepte sind:

- `m5_candle_available`
- `m5_candle_update`
- `m5_agent_trigger`

Der DataContainer aktualisiert zuerst den Candle-Bestand. Analyse-Agenten
sollen erst dann laufen, wenn die Runtime-Bedingungen des jeweiligen Triggers
erfüllt sind.

## Aufgaben des DataContainer

`DataContainer` ist verantwortlich für:

- Speicherung eingehender Candle-Daten
- Aktualisierung existierender Zeitstempel bei Candle-Finalisierung
- Bereitstellung von Candle-Historie
- Resampling höherer Timeframes bei Bedarf
- Gap-Erkennung
- Unterstützung von Indikator- und Snapshot-Workflows

## Warum das für Snapshots wichtig ist

Der Snapshot-Builder nutzt keine versteckte eigene Marktdatenquelle.

Stattdessen verwendet er dieselben Runtime-Daten und Tools, die auf Folgendem
aufbauen:

- `DataContainer`
- `get_candles`
- `calculate_indicator`

Dadurch bleiben:

- Candle-Historie
- Indikatorwerte
- Snapshot-Inhalt
- Agent-seitig sichtbare Tool-Ergebnisse

intern konsistent.

## Resampling

Anfragen nach höheren Timeframes werden zur Laufzeit aus M5-Historie
abgeleitet.

Typische Beispiele:

- letzte `12` M5-Kerzen -> eine H1-Kerze
- letzte `48` M5-Kerzen -> eine H4-Kerze

Der Resampler ist daher sowohl Teil des:

- direkten Runtime-Datenzugriffs
- als auch der Snapshot-Erstellung

## Indikatoren

Indikatoren sind reine Berechnungen und werden über die Tool-Schicht dem
System zugänglich gemacht.

Damit kann dieselbe Indikatorlogik an zwei Stellen verwendet werden:

1. im LLM-Tool-Loop
2. im Snapshot-Builder

Beispiele:

- EMA
- RSI
- ATR
- SMA
- VWAP

## Snapshot-zentrierte Nutzung

Für den aktuellen AA-Decision-Pfad ist der wichtige Datenfluss:

1. Tool-Blöcke laden Candles und Indikatoren
2. Ergebnisse werden in Snapshot-Daten normalisiert
3. Decision-Semantik ergänzt interpretierte Felder
4. Das LLM sieht nur den reduzierten Decision-Payload

Das ist der aktuelle Ersatz für den früheren wiederholten AA-Tool-Call-Zyklus.
