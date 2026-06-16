[Zurück zu Config](ui.config.de.md)

# Bridge Tools

`Bridge Tools` verwaltet Tool-Definitionen, die Agenten-zu-Agenten-Kommunikation über den Event Bus ermöglichen. Ein Bridge Tool erscheint für das LLM wie ein normales Tool — tatsächlich leitet es die Anfrage aber an einen anderen Agenten weiter und gibt dessen Antwort als Tool-Ergebnis zurück. Die Konfiguration wird in `config/RunTime/agent_tools.json5` gespeichert.

---

## Tabelle (Übersicht)

Listet alle konfigurierten Bridge Tools mit: Nummer, Name, Modus, Ziel(e). Ein Klick auf eine Zeile lädt das Tool in den Editor.

---

## Aktionsschaltflächen (Editor-Kopf)

| Schaltfläche | Farbe | Funktion |
|---|---|---|
| **New Empty Tool** | Amber | Leert alle Felder für ein neues Tool |
| **Update** | Grün | Speichert Änderungen am aktuell ausgewählten Tool |
| **Save As New** | Blau | Erstellt ein neues Tool mit dem aktuellen Stand |
| **Delete** | Rot | Löscht das aktuell ausgewählte Tool |

---

## Tool-Editor-Felder

### Name

Eindeutiger Bezeichner des Tools. Erscheint dem LLM als Tool-Name — sollte beschreibend und lowercase_snake_case sein, z. B. `ask_analysis_agent`.

Pflichtfeld. Darf unter allen Bridge Tools nur einmal vorkommen.

### Timeout (Sekunden)

Zahlenfeld. Standard: `90`. Maximale Wartezeit auf die Antwort des Ziel-Agenten. Wenn der Agent nicht innerhalb dieser Zeit antwortet, schlägt der Tool-Aufruf mit einem Timeout-Fehler fehl und das LLM erhält einen beschreibenden Fehlerstring.

### Description

Textfeld. Beschreibt dem LLM was dieses Tool tut. Hat direkten Einfluss auf ob und wann das Modell das Tool aufruft. Sollte klar formulieren welche Art von Fragen oder Aufgaben an den Ziel-Agenten weitergeleitet werden. Eine präzise Description ist entscheidend: Das LLM nutzt sie, um zu entscheiden, ob das Tool für den aktuellen Reasoning-Schritt geeignet ist.

### Question Description

Textarea. Standard: `"Your specific question..."`. Beschreibt dem LLM wie die Frage formuliert sein soll, die an den Ziel-Agenten geschickt wird. Erscheint als Beschreibung des `question`-Arguments in der Tool-Spezifikation.

---

## Modus-Auswahl

### Single Target

Das Tool hat genau einen Ziel-Agenten.

| Feld | Funktion |
|---|---|
| **target_agent_id** | Agent-ID des Ziel-Agenten, z. B. `OAPR1-ALL___-GA-NEWS` |

Das LLM des aufrufenden Agenten gibt eine Freitext-Frage an. Das Bridge Tool sendet diese an das einzelne Ziel und gibt die Antwort zurück.

### Multi Target

Das Tool leitet an mehrere Agenten weiter und lässt das LLM wählen, welches Ziel abgefragt werden soll. Jedes Ziel erscheint als eigene benannte Option in der Tool-Spezifikation.

**Pro Ziel:**

| Feld | Funktion |
|---|---|
| **tool_name** | Name dieser Zieloption wie er dem LLM angezeigt wird, z. B. `ask_news_agent` |
| **target_agent_id** | Agent-ID des Ziel-Agenten, z. B. `GLOBL-ALL___-GA-TA001` |
| **description** | Kurzbeschreibung für das LLM: wann soll diese Option gewählt werden |
| **− (Entfernen)** | Entfernt dieses Ziel |

**+ Add Target** fügt einen neuen leeren Zieleintrag hinzu.

Im Multi-Target-Modus erhält das LLM eine Menge von Sub-Tools unter dem Bridge-Tool-Namen und wählt anhand der Beschreibungen das passende aus.

---

## Sidebar: Live-Vorschau und Validierung

**Live-Vorschau:** Zeigt Name, Modus, Timeout und Ziel-Zusammenfassung.

**Validierung:** Zeigt Fehler wenn Name fehlt, Ziel-Agent-IDs leer sind oder Duplikate vorhanden sind.

---

## Wie Bridge Tools funktionieren

Bridge Tools nutzen das `AGENT_QUERY` / `AGENT_QUERY_RESPONSE`-Nachrichtenpaar des Event Bus für synchrone Agenten-zu-Agenten-Kommunikation.

### Kommunikationsfluss

```
LLM des aufrufenden Agenten
    |
    |  Ruft Bridge Tool auf: ask_ga_market_outlook("Wie ist die DXY-Perspektive?")
    v
Bridge Tool Handler
    |
    |  Sendet: AGENT_QUERY { target_agent_id: "GLOBL-ALL___-GA-ANLYS", question: "..." }
    v
Event Bus (direkt adressierte Zustellung)
    |
    v
Ziel-Agent (GLOBL-ALL___-GA-ANLYS)
    |
    |  Verarbeitet die Anfrage mit eigenem LLM oder eigener Logik
    |  Sendet: AGENT_QUERY_RESPONSE { answer: "DXY befindet sich in einem Abwärtstrend..." }
    v
Event Bus (Antwort zurück zum Ursprungsagenten)
    |
    v
Bridge Tool Handler (im aufrufenden Agenten)
    |
    |  Gibt Antwortstring als Tool-Ergebnis zurück
    v
LLM des aufrufenden Agenten (setzt Reasoning mit empfangenem Kontext fort)
```

Es werden keine Routing-Regeln benötigt. Die Anfrage verwendet direkte Adressierung: Nur der Agent, dessen `agent_id` mit `target_agent_id` übereinstimmt, empfängt das Event.

### Wichtige Eigenschaften

- **Synchron aus LLM-Perspektive**: der Tool-Aufruf blockiert bis die Antwort eintrifft oder der Timeout abläuft
- **Keine Routing-Regel erforderlich**: direkte Adressierung umgeht das Routing-System vollständig
- **Transparent für das LLM**: ein Bridge Tool aufzurufen sieht identisch aus wie jedes andere Tool
- **Antwort als Klartext**: die Antwort des Ziel-Agenten wird als String zurückgegeben, den das LLM in sein Reasoning einbezieht

---

## Wofür werden Bridge Tools verwendet?

Bridge Tools werden hauptsächlich für **hierarchische Analyse** und **agenten-übergreifenden Kontextaustausch** eingesetzt:

### AA-Agent fragt GA-Agenten

Ein AA-Agent (Analyse), der ein bestimmtes Paar analysiert, kann einen GA-Agenten (Global) nach breiterem Marktkontext fragen, der in den eigenen Snapshot-Daten des Paares nicht verfügbar ist. Beispiele:

- DXY-Richtung und -Stärke
- Breite Marktstimmung (Risk-on / Risk-off)
- Bias des wichtigsten korrelierten Instruments
- Liquiditätsbedingungen der aktuellen Handelssession

### AA-Agent fragt einen anderen AA-Agenten

Ein AA-Agent kann den AA-Agenten eines korrelierten Paares abfragen, um zu beurteilen, ob ein Richtungssignal paarspezifisches Rauschen ist oder breite USD-Bewegung widerspiegelt. Beispiele:

- EUR/USD AA fragt GBP/USD AA: "Siehst du auch USD-Schwäche?" — wenn ja, ist das Signal zuverlässiger.
- AUD/USD AA fragt NZD/USD AA zur Bestätigung vor einem Long-Signal.

### BA-Agent Risiko-Gate

Bevor ein BA-Agent (Broker/Action) einen Trade platziert, kann er einen dedizierten Risikomanagement-GA-Agenten abfragen, der offene Positionen, täglichen Drawdown, Korrelationsexposition und Lot-Limits verfolgt. Wenn der Risiko-Agent ablehnt, bricht der BA-Agent den Trade ab.

### Session- und Nachrichtenbewusstsein

Ein Agent kann einen session- oder nachrichtenbewussten Agenten abfragen, um bevorstehende hochimpact-Events, aktuelle Session-Liquiditätsbedingungen oder aktuelle Nachrichten zu prüfen, die ein Paar beeinflussen könnten.

---

## Konfiguration in system.json5

Bridge Tools werden Agenten über die `allowed_tools`-Liste zugewiesen und entweder inline in `tool_config` oder als Top-Level-`bridge_tools`-Liste definiert.

### Methode 1: Inline in `tool_config`

```json
{
  "agents": [
    {
      "agent_id": "OAPR1-EURUSD-AA-ANLYS",
      "tool_config": {
        "allowed_tools": [
          "get_candles",
          "get_indicator",
          "ask_ga_market_outlook"
        ],
        "bridge_tools": {
          "ask_ga_market_outlook": {
            "target_agent_id": "GLOBL-ALL___-GA-ANLYS",
            "description": "Den globalen Analyseagenten nach breiterem Marktkontext, DXY-Richtung und Risikostimmung fragen.",
            "timeout_seconds": 60
          }
        }
      }
    }
  ]
}
```

### Methode 2: Top-Level-`bridge_tools`-Array

Bridge Tools auf Top-Level-Ebene zu definieren ermöglicht die Referenzierung durch mehrere Agenten.

```json
{
  "bridge_tools": [
    {
      "name": "ask_ga_market_outlook",
      "target_agent_id": "GLOBL-ALL___-GA-ANLYS",
      "description": "Breiteren Marktkontext vom GA-Agenten abfragen: DXY, Risikostimmung und breiter USD-Bias.",
      "argument": "question",
      "timeout_seconds": 60
    },
    {
      "name": "ask_gbpusd_aa",
      "target_agent_id": "OAPR1-GBPUSD-AA-ANLYS",
      "description": "Den GBP/USD-AA-Agenten nach seinem aktuellen Bias und wichtigen Levels abfragen.",
      "argument": "question",
      "timeout_seconds": 45
    }
  ]
}
```

---

## Konfigurationsfelder — Referenz

| Feld | Typ | Pflicht | Beschreibung |
|---|---|---|---|
| `name` | string | Ja | Tool-Name, den das LLM zum Aufrufen verwendet. Muss unter allen Bridge Tools eindeutig sein. lowercase_snake_case verwenden. |
| `target_agent_id` | string | Ja | Exakte `agent_id` des abzufragenden Agenten. Muss einem laufenden Agenten im System entsprechen. |
| `description` | string | Ja | Natürlichsprachliche Beschreibung was das Tool tut. Wird in der LLM-Tool-Definition verwendet — klar formulieren, damit das Modell weiß wann es einzusetzen ist. |
| `argument` | string | Nein | Name des einzelnen Arguments, das das LLM übergibt (Standard: `"question"`). |
| `timeout_seconds` | integer | Nein | Wartezeit auf eine Antwort vor Timeout (Standard: `90`). |

### Hinweise zu `target_agent_id`

Die `target_agent_id` muss exakt mit der `agent_id` eines konfigurierten und laufenden Agenten übereinstimmen. Beispiele:

- `GLOBL-ALL___-GA-ANLYS` — globaler Analyseagent
- `OAPR1-EURUSD-AA-ANLYS` — EUR/USD-Analyseagent auf Broker OAPR1
- `OAPR1-GBPUSD-BA-TRADE` — GBP/USD-Broker/Action-Agent

### Hinweise zu `timeout_seconds`

Timeout entsprechend der typischen Antwortzeit des Zielagenten wählen:

| Zielagenten-Typ | Empfohlener Timeout |
|---|---|
| Einfacher Lookup- oder Daten-Agent | 15–20 Sekunden |
| GA-Agent mit Snapshot, ohne Tool-Calls | 30–45 Sekunden |
| GA-Agent mit mehreren Tool-Calls | 60–90 Sekunden |
| Komplexer Multi-Faktor-AA-Agent | 90–120 Sekunden |

Ist der Timeout zu kurz, erhält das aufrufende LLM einen Timeout-Fehler und trifft eine weniger informierte Entscheidung. Ist er zu großzügig, verzögert er den gesamten Analysezyklus des aufrufenden Agenten.

---

## Tool-Definition aus LLM-Perspektive

Wenn ein Bridge Tool konfiguriert und einem Agenten zugewiesen ist, generiert das System automatisch einen Tool-Definitions-Eintrag im System-Prompt-Kontext dieses Agenten. Aus LLM-Perspektive sieht es so aus:

```
Tool: ask_ga_market_outlook
Description: Den globalen Analyseagenten nach breiterem Marktkontext,
             DXY-Richtung und Risikostimmung fragen.
Arguments:
  - question (string): Deine spezifische Frage an den globalen Analyseagenten.
```

Das LLM kann dies an jedem Punkt seines Tool-Use-Loops aufrufen — genauso wie `get_candles` oder `get_indicator`.

---

## Praktische Beispiele

### Beispiel 1: EUR/USD AA fragt GA nach DXY-Kontext

**Szenario**: EUR/USD H1 AA-Agent identifiziert ein potenzielles Long-Setup, ist aber wegen aktueller USD-Stärke in anderen Paaren unsicher.

**Bridge-Tool-Definition** zugewiesen an `OAPR1-EURUSD-AA-ANLYS`:

```json
{
  "name": "ask_dxy_context",
  "target_agent_id": "GLOBL-ALL___-GA-ANLYS",
  "description": "Den globalen Agenten nach aktueller DXY-Stärke, -Richtung und danach fragen, ob der USD-Index die EUR/USD-Aufwärtsbewegung wahrscheinlich unterdrücken wird.",
  "timeout_seconds": 75
}
```

**LLM-Verhalten**: Der EUR/USD AA-Agent ruft auf:

```
ask_dxy_context("Zeigt der DXY aktuell Stärke oder Schwäche? Ist eine weitere Stärkung in den nächsten 2–4 Stunden wahrscheinlich?")
```

Der GA-Agent analysiert seinen eigenen DXY-Snapshot und antwortet. Ist DXY bärisch, hat der EUR/USD AA-Agent mehr Vertrauen in das Long. Ist DXY in einem starken Aufwärtstrend, reduziert der AA-Agent die Konfidenz oder wechselt zu No-Trade.

---

### Beispiel 2: GBP/USD bestätigt USD-Schwäche via EUR/USD

**Szenario**: GBP/USD H1 AA-Agent ist bullish, möchte aber bestätigen, dass das Signal breite USD-Schwäche widerspiegelt und nicht GBP-spezifische Stärke.

**Bridge-Tool-Definition** zugewiesen an `OAPR1-GBPUSD-AA-ANLYS`:

```json
{
  "name": "ask_eurusd_bias",
  "target_agent_id": "OAPR1-EURUSD-AA-ANLYS",
  "description": "Den EUR/USD H1 Analyseagenten nach seinem aktuellen Richtungsbias fragen. Nutzen um zu bestätigen, ob USD-Schwäche breit über Majors vorliegt oder paarspezifisch ist.",
  "timeout_seconds": 60
}
```

**LLM-Verhalten**:

```
ask_eurusd_bias("Was ist dein aktueller Richtungsbias auf EUR/USD? Siehst du auch breite USD-Schwäche?")
```

Bestätigt der EUR/USD AA-Agent USD-Schwäche, erhöht GBP/USD die Konfidenz. Ist EUR/USD flach oder bärisch, behandelt GBP/USD das Signal vorsichtiger.

---

### Beispiel 3: BA-Agent Risiko-Gate vor Trade

**Szenario**: GBP/USD BA-Agent ist bereit einen Long-Order zu platzieren. Vorher fragt er einen Risikomanagement-GA-Agenten, der täglichen Drawdown, Korrelationsexposition und aktive Positionen verfolgt.

**Bridge-Tool-Definition** zugewiesen an `OAPR1-GBPUSD-BA-TRADE`:

```json
{
  "name": "check_risk_clearance",
  "target_agent_id": "GLOBL-ALL___-GA-RISKM",
  "description": "Beim Risikomanagement-Agenten prüfen, ob Budget für einen neuen Trade verfügbar ist. Paar, Richtung und geplante Lot-Größe in der Frage angeben.",
  "timeout_seconds": 30
}
```

**LLM-Verhalten**:

```
check_risk_clearance("GBP/USD long, 0,1 Lots. Ist das tägliche Risikobudget noch verfügbar und gibt es Korrelationskonflikte mit aktuellen offenen Positionen?")
```

Sagt der Risiko-Agent, dass das tägliche Verlustlimit naht oder bereits erhebliches Long-USD-Exposure vorhanden ist, platziert der BA-Agent den Order nicht.

---

### Beispiel 4: Multi-Target Bridge Tool für Nachrichten- und Session-Kontext

**Szenario**: Ein AA-Agent muss je nach Bedarf entweder einen Nachrichten-Agenten oder einen Session-Agenten abfragen.

```json
{
  "name": "ask_context_agent",
  "mode": "multi",
  "timeout_seconds": 45,
  "description": "Einen Kontext-Agenten nach Session- oder Nachrichteninformationen fragen.",
  "targets": [
    {
      "tool_name": "ask_news_agent",
      "target_agent_id": "GLOBL-ALL___-GA-NEWS1",
      "description": "Nach bevorstehenden hochimpact-Wirtschaftsereignissen, aktuellen Nachrichten oder fundamentaler Marktstimmung fragen."
    },
    {
      "tool_name": "ask_session_agent",
      "target_agent_id": "GLOBL-ALL___-GA-SESSN",
      "description": "Nach der aktuellen Handelssession, Liquiditätsbedingungen oder typischer Volatilität zu dieser Tageszeit fragen."
    }
  ]
}
```

Das LLM wählt `ask_news_agent` oder `ask_session_agent` je nachdem, welchen Kontext es aktuell benötigt.

---

### Beispiel 5: Mehrere Bridge Tools an einem Agenten

Ein AA-Agent kann mehrere Bridge Tools gleichzeitig konfiguriert haben. Das LLM entscheidet, welche aufgerufen werden:

```json
{
  "agent_id": "OAPR1-EURUSD-AA-ANLYS",
  "tool_config": {
    "allowed_tools": [
      "get_candles",
      "get_indicator",
      "ask_ga_outlook",
      "ask_gbpusd_correlation",
      "ask_session_agent"
    ],
    "bridge_tools": {
      "ask_ga_outlook": {
        "target_agent_id": "GLOBL-ALL___-GA-ANLYS",
        "description": "Den globalen Analyseagenten nach makroökonomischem Kontext fragen: DXY-Richtung, Risikostimmung und breiter USD-Bias.",
        "timeout_seconds": 75
      },
      "ask_gbpusd_correlation": {
        "target_agent_id": "OAPR1-GBPUSD-AA-ANLYS",
        "description": "Den GBP/USD H1 Agenten nach seinem Bias fragen, um breite USD-Richtung im Gegensatz zu paarspezifischen EUR-Bewegungen zu bestätigen oder zu verwerfen.",
        "timeout_seconds": 60
      },
      "ask_session_agent": {
        "target_agent_id": "GLOBL-ALL___-GA-SESSN",
        "description": "Nach der aktuellen Handelssession, Liquiditätsbedingungen und bevorstehenden Nachrichten-Events in den nächsten 2 Stunden fragen.",
        "timeout_seconds": 20
      }
    }
  }
}
```

---

## Bridge Tools Agenten zuweisen

Eine Bridge-Tool-Definition allein aktiviert das Tool für keinen Agenten. Es muss auch in der `allowed_tools`-Liste des Agenten erscheinen. Ist der Tool-Name nicht in `allowed_tools`, sieht das LLM ihn nicht.

Schritte zur Aktivierung eines Bridge Tools für einen Agenten:

1. Bridge Tool definieren (im Bridge-Tools-Editor oder direkt in `system.json5`)
2. Agent Config für den gewünschten Agenten öffnen
3. Den `name` des Bridge Tools zur `allowed_tools`-Liste des Agenten hinzufügen
4. Agent Config speichern
5. Agenten neu starten oder neu laden

---

## Fehlerbehandlung

| Situation | Was das LLM erhält |
|---|---|
| Ziel-Agent antwortet erfolgreich | Den vollständigen Antworttext des Ziel-Agenten |
| Timeout überschritten | `"[Bridge tool timeout: no response from AGENT_ID within N seconds]"` |
| Ziel-Agent läuft nicht | `"[Bridge tool error: target agent AGENT_ID is not available]"` |
| Ziel-Agent meldet einen Fehler | `"[Bridge tool error: AGENT_ID reported: <Fehlermeldung>]"` |

Der System-Prompt des aufrufenden Agenten sollte beschreiben, wie mit diesen Fällen umzugehen ist. Eine typische Anweisung lautet: "Gibt ein Bridge Tool einen Timeout oder Fehler zurück, mit einem konservativen Urteil basierend auf den verfügbaren Snapshot-Daten fortfahren."

---

## Performance-Überlegungen

- Jeder Bridge-Tool-Aufruf fügt die vollständige Verarbeitungszeit des Ziel-Agenten als Latenz zum Analysezyklus des aufrufenden Agenten hinzu.
- Ketten vermeiden: keine Szenarien schaffen, in denen Agent A Agent B aufruft, der Agent C aufruft — das erzeugt kaskadierende Latenz und Deadlock-Risiko.
- Bridge Tools nur einsetzen, wenn der externe Kontext die Entscheidung wahrscheinlich wesentlich verändert. Enthält der Snapshot bereits ausreichend Daten, fügt ein Bridge-Aufruf nur Latenz ohne Mehrwert hinzu.
- Für zeitkritische Hochfrequenz-Setups (M5-Agenten) können Bridge Tools zu langsam sein. Sie eignen sich besser für H1/H4/D1-Agenten mit längeren Analysezyklen.

---

## Beziehung zu Routing-Regeln

Bridge Tools verwenden **direkte Adressierung** und durchlaufen nicht das Routing-Regeln-System. Die `target_agent_id` ist explizit in der Tool-Konfiguration angegeben. Das ist beabsichtigt:

- Bridge-Tool-Anfragen sind Punkt-zu-Punkt
- Sie geben einen Wert synchron zurück (aus LLM-Perspektive)
- Sie umgehen Event-Routing, Filterung und Transformations-Pipelines
- Der Ziel-Agent empfängt die Anfrage unabhängig von Routing-Regeln, die Events sonst blockieren würden

---

## Typischer Ablauf

1. **New Empty Tool** klicken
2. **Name** vergeben (snake_case, sprechend — das ist was das LLM sieht)
3. **Description** schreiben — spezifisch beschreiben, welche Fragen gestellt werden und wann das Tool eingesetzt werden soll
4. **Modus** wählen: Single oder Multi Target
5. **target_agent_id** eintragen (muss ein existierender, laufender Agent sein)
6. Klare **Question Description** formulieren, um das LLM bei der Fragenformulierung zu leiten
7. **Timeout** entsprechend der erwarteten Antwortzeit des Ziel-Agenten anpassen
8. **Save As New** klicken
9. Agent Config für den Agenten öffnen, der das Tool nutzen soll
10. Namen des Bridge Tools zur **Allowed Tools**-Liste des Agenten hinzufügen

---

## Siehe auch

- [Agent Config](ui.config.agent_config.de.md) — Vollständige Agentenkonfiguration einschließlich Allowed Tools
- [Event Routing](ui.config.event_routing.de.md) — Regelbasiertes Event-Routing (getrennt von Bridge-Tool-Direktadressierung)
- [System Config](ui.config.system_config.de.md) — system.json5 direkt bearbeiten
- [Snapshot Config](ui.config.snapshot_config.de.md) — Wie Agenten-Snapshots vor dem LLM-Aufruf assembliert werden
- [Snapshot-Helferfunktionen](snapshot-helper-functions.de.md) — Python-Helfer für Transform-Scripts
