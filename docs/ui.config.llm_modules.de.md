[Zurück zu Config](ui.config.de.md)

# LLM Modules

LLM Modules ist ein direkter Editor für die Konfigurationsdateien einzelner LLM-Adapter-Module. Jedes Modul hat eine eigene Datei, die hier ausgewählt und bearbeitet werden kann. Diese Seite richtet sich an Operatoren, die LLM-Adapter-Parameter direkt anpassen müssen — Modell-IDs, API-Keys, Endpunkte, Temperature-Standards, Token-Limits, Timeout-Einstellungen und Retry-Verhalten.

---

## Inhaltsverzeichnis

1. [LLM-Architektur-Übersicht](#llm-architektur-übersicht)
2. [Oberfläche](#oberfläche)
3. [Speicherverhalten](#speicherverhalten)
4. [Wie LLM-Module registriert werden](#wie-llm-module-registriert-werden)
5. [Modul-Konfigurationsfelder](#modul-konfigurationsfelder)
6. [Azure-OpenAI-Konfiguration](#azure-openai-konfiguration)
7. [Anthropic-Claude-Konfiguration](#anthropic-claude-konfiguration)
8. [OpenAI-Konfiguration](#openai-konfiguration)
9. [Timeout- und Retry-Einstellungen](#timeout--und-retry-einstellungen)
10. [Mehrere LLM-Module](#mehrere-llm-module)
11. [Sicherheit: API-Key-Handhabung](#sicherheit-api-key-handhabung)
12. [Typischer Ablauf](#typischer-ablauf)
13. [LLM-Modul-Änderungen testen](#llm-modul-änderungen-testen)
14. [LLM-Probleme beheben](#llm-probleme-beheben)

---

## LLM-Architektur-Übersicht

Seit OpenForexAI v0.7 fließt die gesamte LLM-Kommunikation über den Event Bus. Dies ist ein signifikanter Architekturunterschied zu älteren Versionen, in denen Agenten LLMs direkt aufriefen.

### Event-Bus-LLM-Fluss

```
AA-Agent
  → veröffentlicht llm_request auf dem Bus
  → Bus leitet über llm_request-Routing-Regel → LLM-Service
  → LLM-Service (z.B. azure_azmin) ruft Provider-API auf
  → Provider-API gibt Antwort zurück (kann 70–80 Sekunden bei komplexen Prompts dauern)
  → LLM-Service veröffentlicht llm_response auf dem Bus
  → Bus leitet llm_response zurück an den ursprünglichen Agenten
  → Agent verarbeitet Antwort
```

### Bus-Registrierung

Jedes LLM-Modul registriert sich auf dem Bus unter einer eindeutigen Mitglieds-ID. Für ein Modul namens `azure_azmin` lautet die Bus-Mitglieds-ID `llm:azure_azmin`. Routing-Regeln in Event Routing müssen diese ID als Ziel haben.

### Nebenläufigkeit

Mehrere LLM-Anfragen werden gleichzeitig verarbeitet. Jede Anfrage bekommt ihren eigenen asynchronen Task innerhalb des LLM-Services. Eine langsame Anfrage von einem Agenten blockiert nicht die Anfragen anderer Agenten.

### Timeout

Der Standard-Timeout für LLM-Anfragen beträgt 180 Sekunden. Komplexe Prompts mit großen Snapshots dauern typischerweise 70–80 Sekunden. Das 180-Sekunden-Limit bietet einen Sicherheitspuffer. Wenn ein Provider langsam oder nicht erreichbar ist, erhält der Agent einen Timeout-Fehler, protokolliert ihn und wartet auf den nächsten Trigger-Zyklus.

### Agent-zu-LLM-Zuweisung

Jeder Agent gibt an, welches LLM-Modul er über das `llm`-Feld in seiner Agent-Config-Konfiguration verwenden soll. Verschiedene Agenten können gleichzeitig verschiedene LLM-Module verwenden:
- EURUSD-Agent → `azure_azmin` (schnell, kosteneffizient)
- GBPUSD-Agent → `azure_premium` (höherwertiges Modell)
- Test-Agent → `anthropic_claude` (alternativer Provider zum Vergleich)

---

## Oberfläche

### Kopfleiste

| Element | Funktion |
|---------|----------|
| **Modul-Auswahl** | Dropdown mit allen LLM-Modulen aus `modules.llm` der `system.json5` |
| **Dateipfad** | Vollständiger Pfad zur Konfigurationsdatei des gewählten Moduls |
| **Refresh** | Aktuelle Dateiversion von der Festplatte neu laden (nur aktiv wenn Modul gewählt) |
| **Save** | Validieren und Datei schreiben (nur aktiv wenn Modul gewählt) |
| **Position** | Aktuelle Cursor-Position als Zeile:Spalte |

### Modul-Auswahl

Das Dropdown wird aus dem `modules.llm`-Array in `system.json5` befüllt. Jeder Eintrag in diesem Array ist ein Dateipfad; das Dropdown zeigt den Dateinamen-Teil (z.B. `azure_azmin.json5`).

Nach der Auswahl eines Moduls lädt der Editor seinen Dateiinhalt automatisch.

### Zeilennummern

Links im Editor angezeigt. Scrollt synchron mit dem Text.

### Editor-Textarea

Freitext-JSON5-Bearbeitung. Syntax-Hervorhebung:

| Farbe | Angewendet auf |
|-------|---------------|
| Cyan | Objekt-Keys |
| Grün | String-Werte |
| Amber | Boolean-Werte |
| Grau | `null`-Werte |
| Lila | Numerische Werte |

### Status-Meldungen

- **„Saved."** — Datei erfolgreich geschrieben
- **Fehlermeldung** — Parse-Fehler oder Validierungsfehler; Datei nicht geschrieben

---

## Speicherverhalten

1. Inhalt wird als JSON5 geparsed
2. Ergebnis der obersten Ebene muss ein JSON-Objekt sein
3. Bei Fehler: Fehlermeldung angezeigt, Datei nicht geschrieben
4. Bei Erfolg: Datei auf Festplatte geschrieben

Das LLM-Modul übernimmt neue Konfiguration beim nächsten Systemstart oder Modul-Reload. Änderungen an `api_key`, `deployment` oder `model` erfordern einen Systemstart. Änderungen an `default_temperature` und `default_max_tokens` treten nach dem Reload beim nächsten LLM-Aufruf in Kraft.

---

## Wie LLM-Module registriert werden

Der Pfad-Kettenprozess für ein LLM-Modul:

1. `config/system.json5` hat `modules.llm: ["config/llm/azure_azmin.json5"]`
2. Beim Start liest das System diesen Pfad und lädt `azure_azmin.json5`
3. Das Modul wird als LLM-Service instanziiert und als `llm:azure_azmin` auf dem Bus registriert
4. Eine Routing-Regel in Event Routing sendet `llm_request`-Events an `llm:azure_azmin`
5. Agenten, deren `llm`-Feld `azure_azmin` ist, senden ihre LLM-Anfragen an diesen Service

Neues LLM-Modul hinzufügen:
1. Konfigurationsdatei erstellen (z.B. `config/llm/neuer_provider.json5`)
2. Pfad zu `modules.llm` in `system.json5` hinzufügen
3. Routing-Regel hinzufügen, die `llm_request` an `llm:neuer_provider` leitet
4. System neu starten

---

## Modul-Konfigurationsfelder

Alle LLM-Modul-Konfigurationsdateien teilen gemeinsame Felder unabhängig vom Provider:

| Feld | Typ | Pflicht | Beschreibung |
|------|-----|---------|--------------|
| `adapter` | string | ja | Provider-Adapter-Typ: `azure_openai`, `anthropic`, `openai` |
| `name` | string | ja | Modulname (muss dem Dateinamen-Stamm entsprechen, z.B. `azure_azmin`) |
| `default_temperature` | float | nein | Standard-Sampling-Temperature (0,0–2,0). Agenten-spezifische Overrides haben Vorrang. |
| `default_max_tokens` | integer | nein | Standard-maximale Ausgabe-Tokens. |
| `timeout` | integer | nein | Request-Timeout in Sekunden. Standard: 180. |
| `retry_attempts` | integer | nein | Anzahl Retry-Versuche bei flüchtigen Fehlern. Standard: 2. |
| `retry_delay_seconds` | float | nein | Verzögerung zwischen Retries in Sekunden. Standard: 2,0. |
| `prompt_caching` | boolean | nein | Provider-seitiges Prompt-Caching aktivieren (nur Anthropic). Standard: false. |

---

## Azure-OpenAI-Konfiguration

```json5
{
  adapter: "azure_openai",
  name: "azure_azmin",
  endpoint: "https://your-resource.openai.azure.com/",
  api_key_env: "AZURE_OPENAI_API_KEY",
  deployment: "gpt-4o-mini",
  api_version: "2024-08-01-preview",
  default_temperature: 0.3,
  default_max_tokens: 2000,
  timeout: 180,
  retry_attempts: 2,
  retry_delay_seconds: 3.0,
  // Optional: Reasoning-Aufwand für o-Series-Modelle
  // reasoning_effort: "medium",
}
```

### Azure-spezifische Felder

| Feld | Beschreibung |
|------|--------------|
| `endpoint` | Azure-OpenAI-Ressourcen-Endpunkt-URL. Endet mit `/`. |
| `api_key_env` | Name der Umgebungsvariable die den API-Key enthält. Empfohlen gegenüber `api_key`. |
| `api_key` | Klartext-API-Key. Nur verwenden wenn Umgebungsvariablen nicht verfügbar sind. |
| `deployment` | Der in Azure OpenAI Studio erstellte Deployment-Name (nicht der Modellname). |
| `api_version` | Azure-API-Versionsstring. Aktuellste stabile Version verwenden. |
| `reasoning_effort` | Nur für o-Series-Reasoning-Modelle: `"low"`, `"medium"`, `"high"`. Steuert die Tiefe des Chain-of-Thought. |

### Häufige Azure-Deployments

| Modell | Deployment-Beispiel | Anwendungsfall |
|--------|--------------------|----|
| GPT-4o mini | `gpt-4o-mini` | Schnell, kosteneffizient, für die meisten Analysen geeignet |
| GPT-4o | `gpt-4o` | Höhere Qualität, langsamer, teurer |
| o3-mini | `o3-mini` | Reasoning-Modell, sehr leistungsfähig aber höhere Latenz |
| o4-mini | `o4-mini` | Reasoning-Modell mit verbesserter Geschwindigkeit |

---

## Anthropic-Claude-Konfiguration

```json5
{
  adapter: "anthropic",
  name: "anthropic_claude",
  api_key_env: "ANTHROPIC_API_KEY",
  model: "claude-sonnet-4-6",
  default_temperature: 0.3,
  default_max_tokens: 2000,
  timeout: 180,
  retry_attempts: 2,
  retry_delay_seconds: 3.0,
  prompt_caching: true,
  // Optional: Extended Thinking
  // thinking_budget_tokens: 5000,
}
```

### Anthropic-spezifische Felder

| Feld | Beschreibung |
|------|--------------|
| `api_key_env` | Umgebungsvariablenname für den Anthropic-API-Key. |
| `api_key` | Klartext-API-Key (nicht empfohlen). |
| `model` | Modell-ID. Beispiele: `claude-opus-4-5`, `claude-sonnet-4-6`, `claude-haiku-4-5`. |
| `prompt_caching` | Wenn `true`, aktiviert Anthropics Prompt-Caching-Funktion. Reduziert Kosten und Latenz bei wiederholten System-Prompts. Empfohlen: `true`. |
| `thinking_budget_tokens` | Für Extended Thinking: maximale für Chain-of-Thought zugeteilte Tokens. Erhöht die Latenz erheblich. |

### Anthropic-Modellauswahl

| Modell | Geschwindigkeit | Qualität | Kosten |
|--------|-----------------|---------|--------|
| claude-haiku-4-5 | Schnellste | Gut | Niedrigste |
| claude-sonnet-4-6 | Schnell | Sehr gut | Mittel |
| claude-opus-4-5 | Langsamste | Beste | Höchste |

Für Forex-Analyse bietet `claude-sonnet-4-6` eine ausgezeichnete Balance. `prompt_caching: true` für signifikante Kosteneinsparungen aktivieren wenn System-Prompts groß und stabil sind.

---

## OpenAI-Konfiguration

```json5
{
  adapter: "openai",
  name: "openai_gpt4",
  api_key_env: "OPENAI_API_KEY",
  model: "gpt-4o",
  default_temperature: 0.3,
  default_max_tokens: 2000,
  timeout: 180,
  retry_attempts: 2,
  retry_delay_seconds: 3.0,
}
```

### OpenAI-spezifische Felder

| Feld | Beschreibung |
|------|--------------|
| `api_key_env` | Umgebungsvariablenname für den OpenAI-API-Key. |
| `api_key` | Klartext-API-Key (nicht empfohlen). |
| `model` | OpenAI-Modell-ID: `gpt-4o`, `gpt-4o-mini`, `o3-mini` usw. |
| `base_url` | Optionale benutzerdefinierte Basis-URL für OpenAI-kompatible APIs (z.B. lokale LLM-Server). |

---

## Timeout- und Retry-Einstellungen

### Timeout

`timeout: 180` bedeutet, dass das System bis zu 180 Sekunden auf die Antwort des Providers wartet.

Typische Antwortzeiten:
- GPT-4o-mini: 10–30 Sekunden
- GPT-4o: 20–50 Sekunden
- Claude Sonnet: 15–40 Sekunden
- o-Series-Reasoning-Modelle: 60–150 Sekunden
- Claude mit Extended Thinking: 60–180 Sekunden

Wenn Reasoning-Modelle verwendet werden, Timeout nicht unter 150 Sekunden reduzieren.

### Retry

`retry_attempts: 2` bedeutet: wenn der erste Aufruf mit einem flüchtigen Fehler fehlschlägt (Rate-Limit, Timeout, 503), bis zu 2 Mal erneut versuchen (3 Gesamtversuche).

`retry_delay_seconds: 3.0` ist die Wartezeit zwischen Retries.

Fehler die Retry auslösen:
- HTTP 429 (Rate-Limit)
- HTTP 503 (Service nicht verfügbar)
- Netzwerk-Timeout
- Verbindungsabbruch

Fehler die keinen Retry auslösen:
- HTTP 400 (fehlerhafte Anfrage — Prompt zu lang, ungültige Parameter)
- HTTP 401 (Authentifizierungsfehler — falscher API-Key)
- HTTP 404 (Deployment nicht gefunden)

---

## Mehrere LLM-Module

OpenForexAI unterstützt mehrere gleichzeitig laufende LLM-Module.

### Konfiguration

In `system.json5`:
```json5
{
  modules: {
    llm: [
      "config/llm/azure_azmin.json5",
      "config/llm/azure_premium.json5",
      "config/llm/anthropic_claude.json5"
    ]
  }
}
```

### Routing

In Event Routing gezielte Regeln hinzufügen:

| Regel-ID | Event | From | To |
|----------|-------|------|----|
| `default_llm` | `llm_request` | `*` | `llm:azure_azmin` |
| `eurusd_premium_llm` | `llm_request` | `OXS_T-EURUSD-AA-ANLYS` | `llm:azure_premium` |

Die `eurusd_premium_llm`-Regel sollte eine niedrigere Prioritätsnummer haben (wird zuerst ausgewertet), damit EURUSD das Premium-LLM verwendet während alle anderen zu `default_llm` durchfallen.

### Anwendungsfälle für mehrere LLMs

- **Kostenoptimierung**: Hochvolumige Paare an günstigeres Modell leiten, Schlüsselpaare an Premium-Modell
- **Qualitätstests**: Identische Paare auf zwei verschiedenen Modellen gleichzeitig ausführen und Entscheidungslogs vergleichen
- **Failover**: Wenn ein Provider ausfällt, Traffic über Event Routing umleiten ohne Code-Änderungen
- **Provider-Diversifizierung**: Abhängigkeit von einem einzelnen Provider reduzieren

---

## Sicherheit: API-Key-Handhabung

### Umgebungsvariablen-Methode (Empfohlen)

```json5
{
  api_key_env: "AZURE_OPENAI_API_KEY"
}
```

Das System liest die Umgebungsvariable beim Start. Der Key-Wert erscheint nie in Konfigurationsdateien.

### Klartext-Methode (Nicht empfohlen)

```json5
{
  api_key: "sk-dein-key-hier"
}
```

Nur verwenden wenn Umgebungsvariablen nicht verfügbar sind. Der Key erscheint in der Konfigurationsdatei und in jeder Versionskontrollhistorie.

### Key-Rotation

Beim Rotieren eines API-Keys:
1. Umgebungsvariable aktualisieren (oder Klartext-Feld in der Modul-Config)
2. Datei über LLM Modules speichern
3. System neu starten oder Modul neu laden
4. Im [LLM Checker](ui.test.llm_checker.de.md) überprüfen ob Anfragen erfolgreich sind

---

## Typischer Ablauf

### Modell-ID ändern

1. Modul aus dem Dropdown auswählen
2. **Refresh** klicken
3. `deployment` (Azure) oder `model` (Anthropic/OpenAI) ändern
4. **Save** klicken
5. System neu starten
6. Über [LLM Checker](ui.test.llm_checker.de.md) testen

### Temperature anpassen

1. Modul auswählen
2. `default_temperature` ändern (0,0 = deterministisch, 1,0 = kreativ, 0,3 ist ein guter Standard)
3. Speichern
4. Kein Neustart erforderlich — tritt nach Modul-Reload beim nächsten LLM-Aufruf in Kraft

### Neues Modul hinzufügen

1. Neue JSON5-Datei in `config/llm/` erstellen
2. System Config öffnen und Pfad zu `modules.llm` hinzufügen
3. System Config speichern
4. LLM Modules öffnen — neues Modul erscheint im Dropdown
5. Inhalt überprüfen
6. Routing-Regel in Event Routing hinzufügen
7. Neu starten

---

## LLM-Modul-Änderungen testen

Nach jeder Modul-Konfigurationsänderung überprüfen ob das Modul korrekt funktioniert:

1. [LLM Checker](ui.test.llm_checker.de.md) aus dem Test-Menü öffnen
2. LLM-Modul aus dem Modul-Dropdown auswählen
3. Einfachen Test-Prompt eingeben
4. Senden klicken
5. Antwort innerhalb der erwarteten Zeit verifizieren

Der LLM Checker umgeht den Event Bus und ruft das Modul direkt auf — der schnellste Weg um Konnektivität und Authentifizierung zu verifizieren.

---

## LLM-Probleme beheben

### Symptom: LLM-Anfragen laufen häufig in Timeout

- Provider-Statusseite auf Ausfälle prüfen
- `timeout` bei Reasoning-Modellen erhöhen (200+ für o-Series setzen)
- `default_max_tokens` reduzieren wenn Prompts sehr lang sind
- Netzwerkkonnektivität vom Server zum Provider-Endpunkt prüfen

### Symptom: Authentifizierungsfehler (HTTP 401)

- Umgebungsvariable gesetzt und zugänglich?
- Führende/nachfolgende Leerzeichen im Key-Wert prüfen
- Key nicht abgelaufen oder widerrufen?
- Azure: Key gehört zur richtigen Ressource (Endpunkt muss übereinstimmen)

### Symptom: Deployment nicht gefunden (HTTP 404)

- Nur Azure: `deployment`-Feld muss exakt dem Deployment-Namen in Azure OpenAI Studio entsprechen (Groß-/Kleinschreibung beachten)
- Deployment in derselben Region wie Endpunkt?
- `api_version` für dieses Deployment unterstützt?

### Log-Meldungen

| Log-Meldung | Bedeutung |
|-------------|-----------|
| `[LLM] Request received from X, forwarding to provider` | Normal — Anfrage wird verarbeitet |
| `[LLM] Response delivered to X in Ns` | Normal — Antwortzeit in Sekunden |
| `[LLM] Timeout after 180s for request from X` | Provider antwortete nicht rechtzeitig |
| `[LLM] Retry attempt 1/2 for request from X` | Flüchtiger Fehler, Retry |
| `[LLM] Authentication failed for module Y` | API-Key-Problem |
| `[LLM] Rate limited, waiting Ns before retry` | Provider-Rate-Limit erreicht |

---

*Dieses Dokument behandelt LLM Modules in OpenForexAI v0.7+. Zum interaktiven Testen von LLM-Antworten siehe [LLM Checker](ui.test.llm_checker.de.md). Für die Agent-zu-LLM-Zuweisung siehe [Agent Config](ui.config.agent_config.de.md).*
