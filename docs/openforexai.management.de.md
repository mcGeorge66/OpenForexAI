[Zur Dokumentationsübersicht](README.de.md)

# openforexai/management — Management API

Die Management API ist die Steuerebene der laufenden Anwendung. Es handelt sich
um eine FastAPI-Anwendung, die über einen Uvicorn-Background-Task läuft und von
der Web-Konsole für Runtime-Steuerung, Inspektion, Konfigurationsbearbeitung
und Tests verwendet wird.

## Dateien

| Datei | Zweck |
|---|---|
| `api.py` | Endpunkte und Request-/Response-Modelle |
| `server.py` | Hintergrund-Uvicorn-Wrapper für die Runtime |

## Hauptbereiche der API

Die aktuelle API ist deutlich größer als eine reine Health-Schnittstelle. Sie
deckt heute ab:

- Runtime-Status
- Update- und Neustart-Steuerung
- Agent-Execute-/Query-Läufe
- Analyse-Browsing
- Orderbook-Browsing
- Monitoring-Stream-Zugriff
- direkte Tool-Ausführung
- rohe und strukturierte Konfigurationsbearbeitung
- Snapshot-Preview
- selektiven Config-Export/-Import

## System- und Runtime-Endpunkte

Wichtige aktuelle Endpunkte:

| Methode | Pfad | Zweck |
|---|---|---|
| `GET` | `/health` | Grundlegende Health-Informationen |
| `GET` | `/version` | Lokale Anwendungsversion |
| `GET` | `/runtime/status` | Aktueller Runtime-Zustand |
| `GET` | `/metrics` | Zentrale Zähler und Metriken |
| `GET` | `/console/initial` | Daten für die Initial-Seite |
| `GET` | `/system/update/status` | Updater-Status und Ausgabe |
| `POST` | `/system/update/start` | Update-Workflow starten |
| `POST` | `/system/runtime/pause` | Runtime-Verarbeitung pausieren |
| `POST` | `/system/runtime/resume` | Runtime-Verarbeitung fortsetzen |
| `POST` | `/system/restart-now` | Sofortiger Neustart |

## Agent-Endpunkte

| Methode | Pfad | Zweck |
|---|---|---|
| `GET` | `/agents` | Laufende Agenten auflisten |
| `GET` | `/agents/{agent_id}` | Details eines Agenten |
| `POST` | `/agents/{agent_id}/ask` | Normale Agent-Query |
| `POST` | `/agents/{agent_id}/execute` | Inspect-/Testlauf ausführen |
| `GET` | `/agents/{agent_id}/candles` | Candle-Daten für Agent Chat |

### `/agents/{agent_id}/ask`

Dieser Endpunkt wird für normale interaktive Agent-Abfragen verwendet. Die
Runtime veröffentlicht ein `agent_query`-Event und wartet auf die zugehörige
Antwort.

### `/agents/{agent_id}/execute`

Dieser Endpunkt wird von `Agent Chat -> Execute` verwendet.

Er startet einen isolierten Inspect-Lauf und liefert strukturierte Daten
zurück, die die UI in folgende Bereiche aufteilt:

- sichtbare Chat-Ausgabe
- Snapshot-Details
- LLM-Request/Response
- Tool-Traces
- Runtime-Metriken

## Snapshot- und Analyse-Endpunkte

| Methode | Pfad | Zweck |
|---|---|---|
| `POST` | `/config/snapshots/preview` | Snapshot-Preview für einen Agentenkontext bauen |
| `GET` | `/analyses` | Persistierte Analysen auflisten |
| `GET` | `/analyses/{record_id}` | Einzelnen Analyse-Datensatz laden |

Der Snapshot-Preview-Endpunkt wird von `Snapshot Config -> Execute` verwendet.

Er baut den exakten Runtime-Snapshot für den aktuellen, auch ungespeicherten
Profilzustand und liefert sowohl:

- den generierten Snapshot
- als auch den finalen Decision-Input an das LLM

## Orderbook-Endpunkte

| Methode | Pfad | Zweck |
|---|---|---|
| `GET` | `/orderbook` | Orderbook-Einträge auflisten |
| `GET` | `/orderbook/{entry_id}` | Einzelnen Orderbook-Eintrag laden |
| `GET` | `/orderbook/{entry_id}/candles` | Candle-Kontext für einen Eintrag |

Diese Endpunkte treiben `Action -> Orderbook` an und unterstützen Audit sowie
Ausführungsprüfung.

## Monitoring, Tools und Routing

| Methode | Pfad | Zweck |
|---|---|---|
| `GET` | `/monitoring/events` | Monitoring-Event-Puffer |
| `GET` | `/indicators` | Registrierte Indikatoren |
| `GET` | `/tools` | Registrierte Tools |
| `POST` | `/tools/execute` | Tool direkt ausführen |
| `GET` | `/routing/rules` | Aktuelle Routing-Tabelle |
| `POST` | `/routing/reload` | Routing-Konfiguration neu laden |
| `POST` | `/events` | Event in den EventBus injizieren |
| `POST` | `/test/llm/check` | LLM-Konnektivitäts- und Verhaltensprüfung |

## Konfigurations-Endpunkte

Die aktuelle Konfigurationsoberfläche unterstützt sowohl gezielte Editoren als
auch paketartigen Export/Import.

### Rohe und strukturierte Konfiguration

| Methode | Pfad | Zweck |
|---|---|---|
| `GET` | `/config/view` | Maskierte strukturierte Systemansicht |
| `GET` | `/config/system` | Editierbare strukturierte Systemkonfiguration |
| `GET` | `/config/system/text` | Roher `system.json5`-Text |
| `PUT` | `/config/system` | Strukturierte Systemkonfiguration speichern |
| `GET` | `/config/files/{name}` | Strukturierte Runtime-Datei laden |
| `GET` | `/config/files/{name}/text` | Roher Runtime-Dateitext |
| `PUT` | `/config/files/{name}` | Runtime-Konfigurationsdatei speichern |
| `GET` | `/config/modules/{module_type}` | Konfigurierte Module auflisten |
| `GET` | `/config/modules/{module_type}/{name}` | Maskierte Modulkonfiguration |
| `GET` | `/config/modules/{module_type}/{name}/raw` | Strukturierte Roh-Modulkonfiguration |
| `GET` | `/config/modules/{module_type}/{name}/raw_text` | Roher Modultext |
| `PUT` | `/config/modules/{module_type}/{name}/raw` | Roh-Modulkonfiguration speichern |
| `GET` | `/config/information/readme` | Information-Seiteninhalt lesen |
| `PUT` | `/config/information/readme` | Information-Seiteninhalt speichern |

### Package-Manager-Unterstützung

| Methode | Pfad | Zweck |
|---|---|---|
| `POST` | `/config/packages/export` | Ausgewählte Bereiche exportieren |
| `POST` | `/config/packages/validate` | Importpaket validieren |
| `POST` | `/config/packages/import` | Ausgewählte Bereiche importieren |

Aktuell unterstützte Paketbereiche:

- Agents
- Snapshot Profiles
- Decision Prompt Profiles
- Bridge Tools
- Event Routing
- System Config

## Authentifizierung

Die API kann über `X-API-Key` geschützt werden, wenn `MANAGEMENT_API_KEY`
gesetzt ist. Ohne diese Variable bleibt die API für lokale Entwicklung offen.

## Server-Integration

`server.py` führt Uvicorn als nicht blockierenden Hintergrund-Task innerhalb
des Haupt-Event-Loops aus. Die Management API läuft also parallel zu:

- EventBus
- Brokern
- Agenten
- Monitoring
- ConfigService

Die API ist kein separates Steuerungsprogramm, sondern Teil der laufenden
Runtime.
