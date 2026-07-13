[Zur Dokumentationsübersicht](README.de.md)

# openforexai/agents — Agenten-Laufzeit

OpenForexAI verwendet für alle Agententypen genau eine Laufzeitklasse:

- `openforexai/agents/agent.py`

`AA`, `BA` und `GA` sind konfigurationsgesteuerte Varianten derselben Klasse.
Es gibt im aktiven Laufzeitpfad keine rollenspezifischen Unterklassen.

## Was einen Agenten steuert

Ein Agent wird hauptsächlich über die von `ConfigService` gelieferte
Konfiguration definiert.

Wichtige Felder sind:

- `type`
- `llm`
- `broker`
- `pair`
- `event_triggers`
- `AnyCandle`
- `system_prompt`
- `tool_config`
- `snapshot_profile`
- `decision_prompt_profile`

## Bootstrap-Ablauf

Beim Start erhält der Agent seine vollständige Konfiguration nicht direkt im
Konstruktor, sondern über den EventBus.

1. Der Agent veröffentlicht `agent_config_requested`.
2. `ConfigService` antwortet mit `agent_config_response`.
3. Der Agent löst daraus LLM, Broker und erlaubte Tools auf.
4. Danach starten Nachrichten-Loop und optionaler Timer-Loop.

## Snapshot-gestützte Laufzeitpfade

Die Live-Runtime unterstützt inzwischen snapshotgestützte Ausführung für
mehrere Agententypen. Das konkrete Verhalten hängt weiterhin von Rolle,
Trigger und Tool-Policy ab.

Der Analyse-Agent (`AA`) besitzt derzeit die stärkste Spezialisierung.

### 1. Snapshot-basierter Decision-Only-Pfad

Dies ist der aktuelle Produktionspfad für Marktanalysen.

Er wird verwendet, wenn ein Trigger über die Decision-Only-Snapshot-Engine
laufen soll, zum Beispiel bei `m5_agent_trigger`.

Ablauf:

1. Die Runtime baut mit `build_analysis_snapshot(...)` einen Marktsnapshot.
2. Das Snapshot-Profil bestimmt, welche Tools genutzt werden und wie die Daten geformt werden.
3. Das Decision-Prompt-Profil bestimmt den finalen system_prompt für den Decision-Run.
4. Das LLM erhält genau einen vorbereiteten User-Payload statt einer mehrstufigen Tool-Konversation.
5. Der Agent persistiert und veröffentlicht das finale `analysis_result`.

### 2. Snapshot-gestützter Tool-Loop und Standard-Tool-Loop

Für Agent Queries, Broker-Agenten, Global-Agenten oder allgemein für
snapshotfähige Agenten, die weiterhin explizite Aktionstools benötigen, kann
die Runtime den klassischen Tool-Loop weiterverwenden.

In diesem Modus kann die Runtime trotzdem einen vorbereiteten Snapshot in den
Prompt injizieren, während die Tool-Nutzung für explizite Aktionen oder
Sonderfälle erhalten bleibt.

Der tool-fähige Pfad:

- sendet Gesprächsverlauf plus sichtbare Tool-Schemas an das LLM
- führt genehmigte Tool-Aufrufe über den `ToolDispatcher` aus
- hängt Assistant- und Tool-Turns an, bis eine finale Antwort erzeugt ist

## Snapshot- und Decision-Profile

Der aktuelle Agenten-Workflow unterstützt zwei Profiltypen, die in
`config/system.json5` aufgelöst werden.

### `snapshot_profile`

Wählt ein benanntes Snapshot-Profil aus `snapshot_profiles`.

Das aufgelöste Profil steuert:

- welche gemeinsamen Tools ausgeführt werden
- feste Tool-Argumente
- Form des Decision-Payloads
- Decision-Semantik
- Token-sparende Include-Optionen

### `decision_prompt_profile`

Wählt ein benanntes Prompt-Profil aus `decision_prompt_profiles`.

Das Profil steuert, wie der normale Agent-Prompt für snapshotgestützte Läufe
ersetzt oder erweitert wird.

Damit kann die Runtime für AA-, BA- oder GA-Läufe einen viel saubereren
snapshotbezogenen Ausführungsprompt injizieren.

## Agent-Trigger

Häufige aktuelle Trigger sind:

- `m5_agent_trigger`
- `prompt_updated`
- `agent_query`
- `analysis_result` für Broker-Agenten

`AnyCandle` teilt M5-Trigger, damit ein Analyse-Agent zum Beispiel nur auf
jede dritte M5-Aktualisierung reagiert.

## Ausgabe des Analyse-Agenten

Wenn ein AA erfolgreich abschließt, dann:

- persistiert er das Analyseergebnis im Repository
- speichert den Marktsnapshot zusammen mit dem Analyse-Datensatz
- veröffentlicht `analysis_result` auf dem EventBus

Ist der Snapshot ungültig, geht der Lauf nicht weiter zum LLM. Stattdessen
sendet die Runtime Monitoring-Informationen und überspringt den Zyklus.

## Verhalten des Broker-Agenten

Der aktuelle Broker-Agent (`BA`) ist ausführungsorientiert.

Er empfängt ein `analysis_result` und:

- validiert den Payload
- prüft Konto- und Positionsstatus
- kann Broker- und Account-Tools aufrufen
- kann abhängig von Prompt und Tool-Ergebnissen Trades eröffnen oder schließen

Der BA kann ebenfalls Snapshot-Profile verwenden. In diesem Fall dient der
Snapshot als vorbereiteter Ausführungskontext, während der BA für explizite
Brokeraktionen wie Open oder Close tool-fähig bleibt.

## Agent Query vs. Execute Inspection

Die UI unterscheidet jetzt zwei Arten der Agent-Interaktion.

### Agent Query

`Send` in Agent Chat nutzt den normalen Query-Pfad und liefert die Antwort des
Agenten zurück.

### Execute Inspection

`Execute` in Agent Chat startet einen isolierten Inspect-Lauf und liefert:

- sichtbare Chat-Ausgabe in der linken Historie
- Run-Details für Snapshot, LLM, Tools und Runtime im Inspector unter dem Chart

Damit lassen sich Konfigurationen gezielt testen, ohne nur auf echte
Live-Events angewiesen zu sein.
