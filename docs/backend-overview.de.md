[Zur Dokumentationsübersicht](README.de.md)

# Backend-Übersicht

Dieses Dokument ist die technische Übersicht über das OpenForexAI-Backend.

Verwende es, wenn du verstehen willst, wie die Runtime aufgebaut ist, wie
Daten durch das System fließen und an welcher Stelle Backend-Verhalten
implementiert oder debuggt wird. Die anwendungsorientierte Bedienung ist
separat dokumentiert im [UI-Handbuch](ui.de.md).

## Zweck

Das Backend ist verantwortlich für:

- Laden der Konfiguration
- Bootstrap von Adaptern und Agenten
- Sammeln und Resampling von Marktdaten
- Bauen von Decision-Snapshots
- Ausführen von LLM-gestützten Agentenzyklen
- Ausführen und Synchronisieren von Trading-Aktionen
- Persistieren von Domänendaten
- Bereitstellen der Management API

## Zentrale Runtime-Komponenten

Die aktuelle Runtime besteht im Kern aus:

- `bootstrap.py`
- `ConfigService`
- `EventBus`
- `RoutingTable`
- `DataContainer`
- konfigurierten Broker-Adaptern
- konfigurierten LLM-Adaptern
- dem Management-API-Server
- einer gemeinsam genutzten `Agent`-Klasse, die vielfach mit
  unterschiedlicher Konfiguration instanziiert wird

## Architekturprinzipien

### Konfigurationsgetriebene Runtime

Agenten, Module, Routing, Snapshot-Profile und Decision-Prompt-Profile werden
über Konfiguration definiert und nicht über viele Spezialklassen.

### Eine gemeinsame Agentenklasse

AA, BA und GA sind weiterhin nur Bezeichner. Das Verhalten entsteht durch die
Konfiguration des Agenten und nicht durch getrennte Implementierungen.

### Tool-Registry als gemeinsamer Erweiterungspunkt

Tool-Plugins sind der gemeinsame Erweiterungspunkt für:

- Agenten-Tool-Nutzung
- Snapshot-Tool-Blöcke
- direkte Ausführung über den UI Tool Executor

Dadurch kann eine Tool-Implementierung an mehreren Stellen der Runtime
wiederverwendet werden.

### Snapshot-basierter AA-Decision-Flow

Der AA-Pfad ist nicht mehr primär auf einen langen Tool-Loop innerhalb des LLM
ausgelegt. Stattdessen baut die Runtime einen vorbereiteten Decision-Snapshot
und das LLM arbeitet primär als Decision Engine über diesem Snapshot.

### Brokerbestätigte Orderbook-Daten

Das lokale Orderbook ist eine lokale Kopie, aber brokerbestätigte Zeitstempel
und finale Trade-Werte gelten dort als autoritative Quelle, sobald sie
vorliegen. Lokale UTC-Request-Zeitstempel bleiben als vorläufige
Prozesszeitpunkte erhalten.

## Konfigurationsebenen

Wichtige Konfigurationsebenen sind:

- zentrale Runtime-Konfiguration in `config/system.json5`
- Broker-Modulkonfigurationen in `config/modules/broker/`
- LLM-Modulkonfigurationen in `config/modules/llm/`
- Event-Routing-Regeln
- Snapshot-Profile
- Decision-Prompt-Profile

Siehe auch:

- [Konfigurationsleitfaden](config.de.md)
- [Snapshot-Konfigurationsleitfaden](snapshot-config-guide.de.md)

## Agenten-Laufzeitfluss

Auf hoher Ebene sieht ein Agentenablauf so aus:

1. Der Agent fordert seine Konfiguration an.
2. Der ConfigService liefert die aufgelöste Konfiguration zurück.
3. Der Agent löst Broker-, LLM- und Tool-Kontext auf.
4. Der Agent wartet auf Nachrichten oder UI-gesteuerten Execute-Input.
5. Je nach Konfiguration und Nachrichtentyp kann er:
   - einen Snapshot bauen
   - eine LLM-Entscheidung ausführen
   - Tools ausführen
   - ein Ergebnis oder Runtime-Event publizieren

Für snapshotbasierte AA-Zyklen ist der Normalfluss:

1. Die Runtime sammelt die benötigten Marktdaten.
2. Die Runtime führt die konfigurierten Snapshot-Tool-Blöcke aus.
3. Die Runtime leitet semantische Felder und Validierungsflags ab.
4. Die Runtime baut den Decision Payload.
5. Das LLM liefert die finale strukturierte Entscheidung.

## Snapshot- und Decision-Pipeline

Das Snapshot-System ist aktuell eine der wichtigsten Backend-Änderungen.

Seine Aufgaben sind:

- ein benanntes Snapshot-Profil laden
- die konfigurierten Tool-Blöcke ausführen
- echte Markt- und Indikatordaten sammeln
- semantische Felder wie Trend, RSI-State, Support/Resistance und Entry-Gates
  ableiten
- den finalen Decision Payload bauen
- bei Bedarf umfangreichere Preview-Daten an die UI geben

Wichtige Trennung:

- Preview-/Debug-Daten dürfen mehr Struktur enthalten
- der finale Decision Payload für das LLM wird bewusst auf die für die
  Entscheidung nötigen Felder reduziert

## Management API

Die Management API ist die Integrationsoberfläche der Web-Konsole.

Sie wird verwendet für:

- Lesen und Schreiben von Konfiguration
- Listen und Bearbeiten von Agenten
- Bearbeiten von Snapshot- und Decision-Prompt-Profilen
- Paket-Import/Export
- Orderbook-Zugriff
- Monitor-Subscriptions
- Execute-Preview-artige Hilfsaufrufe

Technische API-Details sind weiter dokumentiert in:

- [Management API](openforexai.management.de.md)

## Orderbook und Broker-Synchronisierung

Das Orderbook-Backend unterscheidet aktuell zwischen:

- lokalen UTC-Request-Zeitstempeln
- brokerbestätigten Open-/Close-Zeitstempeln
- vorläufigen lokalen Datensätzen
- synchronisierten brokerbestätigten Datensätzen

Das ist wichtig, weil:

- Broker-Zeitstempel zur Candle-Zeit passen
- lokale Zeitstempel zeigen, was die Runtime versucht hat
- unbestätigte Datensätze später gegen die Brokerquelle abgeglichen werden
  können

## Beziehung zur UI

Die UI ist kein zweites Backend. Sie konsumiert Backend-Zustand.

Das bedeutet:

- die UI soll anzeigen, was das Backend aufgelöst hat
- die UI soll keinen technischen Zustand erfinden
- Inspektionsansichten wie Agent Chat oder Orderbook sollen die Backend-Wahrheit
  möglichst klar sichtbar machen

## Empfohlene Lesereihenfolge

Wenn du neu im Projekt bist, lies in dieser Reihenfolge:

1. [Konfigurationsleitfaden](config.de.md)
2. [UI-Handbuch](ui.de.md)
3. [Agentensystem](openforexai.agents.de.md)
4. [Marktdatenfluss](openforexai.data.de.md)
5. [Management API](openforexai.management.de.md)
6. [Snapshot-Konfigurationsleitfaden](snapshot-config-guide.de.md)

## Zugehörige technische Dokumente

- [Agentensystem](openforexai.agents.de.md)
- [Marktdatenfluss](openforexai.data.de.md)
- [Management API](openforexai.management.de.md)
- [Datenbank-Hinweise](database.en.md)
- [Testüberblick](tests.en.md)
