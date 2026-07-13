[Zur Dokumentationsübersicht](README.de.md)

# Konfigurationsleitfaden

Das Verzeichnis `config/` ist die operative Wahrheitsquelle von OpenForexAI.

Es enthält:

- die zentrale Runtime-Konfiguration
- zur Laufzeit editierbare Bridge-/Routing-Dateien
- LLM-Modulkonfigurationen
- Broker-Modulkonfigurationen
- Sample- und Meta-Dateien für die Modulerstellung

## Verzeichnisstruktur

```text
config/
  system.json5
  config.default.json5
  RunTime/
    agent_tools.json5
    event_routing.json5
  modules/
    broker/
      *.sample.json5
      *.meta.json5
    llm/
      *.sample.json5
      *.meta.json5
```

## `system.json5`

`system.json5` ist das zentrale Live-Konfigurationsdokument.

Wichtige aktuelle Top-Level-Bereiche sind:

- `system`
- `modules`
- `snapshot_profiles`
- `decision_prompt_profiles`
- `agents`

Je nach Deployment können zusätzlich Bereiche wie `system`, `database`,
`data` oder Import-Regeln vorhanden sein, die ebenfalls von UI und Package
Manager verarbeitet werden.

### `system`

Dieser Bereich enthält laufzeitweite Infrastruktur-Einstellungen.

Wichtige aktuelle Unterbereiche sind:

- `management_api`
- `ui.dev_server`

Beispiel:

```json
"system": {
  "management_api": {
    "host": "127.0.0.1",
    "port": 8765
  },
  "ui": {
    "dev_server": {
      "host": "127.0.0.1",
      "port": 5173
    }
  }
}
```

Bedeutung:

- `system.management_api.port` steuert den FastAPI-/Backend-Port
- `system.ui.dev_server.port` steuert den Vite-/Browser-Port im Dev-Betrieb
- auch der Vite-Proxy liest `system.management_api.host` und `system.management_api.port`

Damit können mehrere lokale Instanzen parallel laufen, solange jede Instanz
eigene Portpaare verwendet.

### `modules`

Dieser Bereich mappt logische Modulnamen auf konkrete Konfigurationsdateien.

Aktuelles Beispiel:

```json
"modules": {
  "llm": {
    "azure_azmin": "config/modules/llm/azure.azmin.json5"
  },
  "broker": {
    "mt5_oxs_t": "config/modules/broker/mt5.oxs_t.json5"
  }
}
```

Agenten referenzieren diese Namen, anstatt Verbindungsdetails direkt
einzubetten.

### `snapshot_profiles`

Dieser Bereich enthält benannte Snapshot-Definitionen, die als
laufzeitvorbereiteter Prompt-Kontext für Agenten verwendet werden.

Ein Snapshot-Profil kann definieren:

- Beschreibung
- `decision_input_prefix`
- `decision_payload`
- `decision_semantics`
- `recent_context`
- `include_sections`
- `tool_blocks`
- optionale strategiespezifische Formungswerte

Snapshot-Profile werden in `Agent Config` ausgewählt und in `Snapshot Config`
bearbeitet.

### `decision_prompt_profiles`

Benannte Prompt-Profile für snapshotgestützte Agentenläufe.

Ein Prompt-Profil enthält typischerweise:

- Beschreibung
- `mode`
- `prompt`

Typische `mode`-Werte:

- `replace`
- `append`

Damit kann die Runtime trotz eines normalen Agent-Prompts in der Konfiguration
für Snapshot-Läufe einen viel saubereren Decision-Prompt injizieren.

### `agents`

Jeder laufende Agent besitzt hier einen Eintrag.

Wichtige aktuelle Felder sind unter anderem:

- `enable`
- `type`
- `llm`
- `broker`
- `pair`
- `timer`
- `event_triggers`
- `AnyCandle`
- `snapshot_profile`
- `decision_prompt_profile`
- `system_prompt`
- `tool_config`

Aktuelle AA-Konzepte:

- `event_triggers` enthält `m5_agent_trigger`, `prompt_updated`, `agent_query`
- `snapshot_profile` verweist auf ein Snapshot-Profil
- `decision_prompt_profile` verweist auf ein Decision-Prompt-Profil

Aktuelle BA-Konzepte:

- `event_triggers` enthält `analysis_result` und `agent_query`
- ein Snapshot-Profil kann vorbereiteten Broker-/Account-/Orderbook-Kontext
  einspeisen, statt diesen Kontext bei jedem Lauf separat per Tool zu holen

## Runtime-Dateien in `config/RunTime`

### `agent_tools.json5`

Wird für Bridge-Tool-artige Runtime-Konfiguration verwendet.

Diese Datei wird über die UI unter `Bridge Tools` bearbeitet.

### `event_routing.json5`

Definiert die Routing-Regeln des EventBus.

Diese Datei wird über die UI unter `Event Routing` bearbeitet und kann über die
Management API zur Laufzeit neu geladen werden.

## Modulkonfigurationsdateien

Broker- und LLM-Verbindungsdetails liegen in `config/modules/...`.

Diese Dateien werden bearbeitet über:

- `Broker Modules`
- `LLM Modules`

Wichtige Punkte:

- aktive Module werden über Namen aus `system.json5` referenziert
- Sample-Dateien dokumentieren Pflichtfelder
- Meta-Dateien beschreiben Struktur und UI-Hinweise

## Beziehung zu UI und Package Manager

Die aktuelle UI behandelt Konfiguration nicht mehr als einen einzigen großen
Textblock.

Stattdessen gilt:

- `Agent Config` bearbeitet Agenteneinträge
- `Snapshot Config` bearbeitet `snapshot_profiles`
- `Decision Prompt` bearbeitet `decision_prompt_profiles`
- `Bridge Tools` bearbeitet Runtime-Tool-Konfiguration
- `Event Routing` bearbeitet Routing-Regeln
- `System Config` bearbeitet die zentrale Systemdatei
- `Helper Config` bearbeitet `config/snapshot_helpers.py`
- `Package Manager` exportiert/importiert ausgewählte Konfigurationsbereiche

## Export-/Import-Bereiche des Package Managers

Der aktuelle Package Manager unterstützt selektiven Export/Import von:

- Agents
- Snapshot Profiles
- Decision Prompt Profiles
- Bridge Tools
- Event Routing
- System Config

So kann eine Strategiekonfiguration verschoben werden, ohne die komplette
Installation exportieren zu müssen.

## Umgebungsvariablen

Konfigurationsdateien verwenden `${VAR}` oder `${VAR:-default}`-Ersetzung.

Typische Variablen sind:

- LLM-API-Keys und Endpunkte
- Broker-Zugangsdaten
- Datenbankeinstellungen
- Log-Level

Geheimnisse sollten außerhalb versionierter Konfigurationsdateien liegen.
