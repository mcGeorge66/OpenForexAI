[Zur Dokumentationsübersicht](README.de.md)

# OpenForexAI — Benutzerhandbuch

Willkommen im OpenForexAI-Benutzerhandbuch. Dieses Dokument ist der zentrale Einstiegspunkt zum Verstehen, Konfigurieren und Betreiben des automatisierten Handelssystems OpenForexAI.

---

## Inhaltsverzeichnis

1. [Was ist OpenForexAI?](#was-ist-openforexai)
2. [Systemüberblick](#systemüberblick)
3. [Schnellstart-Anleitung](#schnellstart-anleitung)
4. [Navigationsstruktur](#navigationsstruktur)
5. [Systemarchitektur](#systemarchitektur)
6. [Der Handels-Workflow](#der-handels-workflow)
7. [Strategie-Empfehlungen](#strategie-empfehlungen)
8. [Sicherheitsrichtlinien](#sicherheitsrichtlinien)
9. [Abschnittsindex](#abschnittsindex)

---

## Was ist OpenForexAI?

OpenForexAI ist ein vollautomatisiertes Forex-Handelssystem, das drei wesentliche Fähigkeiten in einer einheitlichen, ereignisgesteuerten Pipeline vereint:

**1. Broker-Konnektivität (MT5 / OANDA)**
OpenForexAI verbindet sich direkt mit MetaTrader 5 (MT5) oder der OANDA-REST-API, um Marktdaten in Echtzeit zu empfangen und Orders auszuführen. Das gesamte Ordermanagement — Platzieren, Ändern und Schließen von Positionen — erfolgt automatisch über die Broker-Adapterschicht.

**2. KI-gestützte Marktanalyse (Azure OpenAI / Anthropic)**
Das Herzstück von OpenForexAI ist ein KI-Agentensystem. Jeder konfigurierte Analyse-Agent (AA-Agent) erhält einen umfangreichen Markt-Snapshot — mit Preisdaten, technischen Indikatoren, Swing-Levels, Session-Kontext, Makro-News und mehr — und befragt ein Large Language Model (LLM), um die aktuelle Marktsituation zu bewerten und ein Handelssignal zu erzeugen.

**3. Ereignisgesteuerte Ausführung**
Das System basiert auf einem zentralen Event Bus. Jede Information — eine neue Kerze, eine abgeschlossene Analyse, ein Risiko-Check-Ergebnis, ein ausgeführter Trade — wird als Event veröffentlicht. Module abonnieren die für sie relevanten Events und reagieren entsprechend. Dieses entkoppelte Design ermöglicht die unabhängige Konfiguration und Testbarkeit jeder Komponente.

OpenForexAI ist für Trader konzipiert, die disziplinierte, regelbasierte Strategien automatisieren möchten und dabei die vollständige Kontrolle über Parameter, Prompts und Risiko-Einstellungen behalten. Es ist kein Black-Box-Signal-Service — jede Entscheidung der KI wird protokolliert, ist nachvollziehbar und kann angepasst werden.

---

## Systemüberblick

Das System läuft in einer kontinuierlichen Schleife:

```
Marktdaten → Kerzen-Event → Analyse-Agent → Signal-Event → Ausführungs-Agent → Broker
```

Genauer:

1. **Marktdaten-Feed**: Der Broker-Adapter streamt Live-Kerzendaten für jedes konfigurierte Handelspaar. Wenn eine Kerze schließt (typischerweise M5 — 5 Minuten), wird ein Kerzen-Event auf dem Event Bus veröffentlicht.

2. **Snapshot-Assembly**: Ein AA-Agent, der Kerzen-Close-Events abonniert hat, baut einen umfassenden Markt-Snapshot zusammen. Dieser Snapshot aggregiert Daten aus mehreren Quellen: Preisverlauf, ATR, Swing-Highs/-Lows, Trend-Erkennung, News-Events, Session-Überschneidungen und benutzerdefinierte Indikatoren.

3. **LLM-Analyse**: Der zusammengestellte Snapshot wird an das konfigurierte LLM (Azure OpenAI GPT-4o oder Anthropic Claude) gesendet. Der Decision Prompt des Agenten definiert die Systeminstruktionen. Das LLM gibt eine strukturierte Analyse zurück, die Signalrichtung, Konfidenz, Einstiegsparameter und Begründung enthält.

4. **Signal-Filterung**: Der EC Relay (Event Coordinator Relay) wendet regelbasierte Filter auf das rohe Signal an. Diese können Tageszeit-Einschränkungen, News-Sperrzeiträume, maximale gleichzeitige Trade-Limits und Risikobudget-Prüfungen umfassen.

5. **Trade-Ausführung**: Wenn das Signal alle Filter besteht, empfängt der BA-Agent (Broker Adapter Agent) ein Ausführungs-Event und platziert den Trade über die Broker-API. Stop-Loss- und Take-Profit-Levels werden aus ATR-Werten im Snapshot berechnet.

6. **Position-Management**: Offene Positionen werden kontinuierlich überwacht. Trailing Stops, Teilschließungsregeln und zeitbasierte Exits werden mit jeder weiteren Kerze angewendet.

7. **Logging und Monitoring**: Jedes Event, jede LLM-Antwort, jede Orderaktion wird im Event-Log gespeichert. Die Monitor-UI bietet einen Echtzeit-Stream aller Aktivitäten.

---

## Schnellstart-Anleitung

### Schritt 1: System-Status prüfen

Navigiere zum **Monitor**-Bereich ([Event Stream](ui.monitor.de.md)). Du solltest einen kontinuierlichen Stream von Events sehen, der mit dem Schließen neuer Kerzen erscheint. Die wichtigsten Events, auf die du achten solltest:

- `candle_closed` — bestätigt, dass Marktdaten fließen
- `snapshot_built` — bestätigt, dass der AA-Agent Snapshots zusammenstellt
- `llm_response_received` — bestätigt, dass das LLM antwortet
- `signal_evaluated` — bestätigt, dass der EC Relay ein Signal verarbeitet hat

Fehlen diese Events, prüfe die System-Config auf Verbindungsprobleme.

### Schritt 2: Agenten-Konfiguration prüfen

Gehe zu **Config → Agent Config** ([Agent Config](ui.config.agent_config.de.md)). Stelle sicher, dass mindestens ein AA-Agent aktiv ist, dem richtigen Handelspaar zugewiesen ist und mit einem gültigen LLM-Modul verbunden ist.

### Schritt 3: Ersten Trade lesen

Wenn ein Trade platziert wird, siehst du ein `order_placed`-Event im Monitor. Klicke auf das Event, um es aufzuklappen. Du siehst:

- **Symbol**: das Handelspaar (z. B. EURUSD)
- **Richtung**: BUY oder SELL
- **Einstiegspreis**: der Preis, zu dem die Order platziert wurde
- **Stop Loss**: ATR-basiertes Stop-Level
- **Take Profit**: Ziel-Level
- **Konfidenz**: der Konfidenzwert des LLM (0–100)
- **Begründung**: eine Textzusammenfassung des LLM, die erklärt, warum dieser Trade eingegangen wurde

### Schritt 4: Offene Positionen prüfen

Navigiere zu **Action → Orderbook** ([Orderbook](ui.action.orderbook.de.md)), um alle offenen Positionen mit Live-P&L-Updates zu sehen.

### Schritt 5: Bei Bedarf anpassen

Wenn du ändern möchtest, wie die KI den Markt analysiert, gehe zu **Config → Decision Prompt** ([Decision Prompt](ui.config.decision_prompt.de.md)) und prüfe den System-Prompt. Wenn du Risikoparameter ändern möchtest, gehe zu **Config → Agent Config**.

---

## Navigationsstruktur

Die OpenForexAI-UI ist in vier Hauptbereiche gegliedert:

### Action
Die operative Oberfläche. Verwende diese Seiten während des Live-Handels, um Aktivitäten zu überwachen, Positionen zu prüfen, KI-Analysen einzusehen und mit Agenten zu interagieren.

| Seite | Zweck |
|-------|-------|
| [Initial](ui.action.initial.de.md) | Dashboard-Übersicht und System-Status |
| [Agent Chat](ui.action.chat.de.md) | Direkte Chat-Oberfläche mit KI-Agenten |
| [Orderbook](ui.action.orderbook.de.md) | Live-Positionen und Trade-Verlauf |
| [Chart Analysis](ui.action.chart_analysis.de.md) | Visueller Chart mit KI-Analyse-Overlay |

### Monitor
Echtzeit-Systembeobachtung. Verwende diese Seiten zur Diagnose von Problemen, zur Verifikation des korrekten Systembetriebs und zur Prüfung vergangener Entscheidungen.

| Seite | Zweck |
|-------|-------|
| [Event Stream](ui.monitor.de.md) | Live-Feed aller System-Events |

### Config
Konfigurationsverwaltung. Verwende diese Seiten, um das Systemverhalten zu definieren — welche Paare gehandelt werden, wie die KI argumentiert, wie das Risiko verwaltet wird und wie Events geroutet werden.

| Seite | Zweck |
|-------|-------|
| [Agent Config](ui.config.agent_config.de.md) | Agenten-Definitionen, Paare, LLM-Bindungen, Risiko-Einstellungen |
| [Entity Config](ui.config.entity_config.de.md) | Handelbare Entitäten (Symbole) konfigurieren |
| [Snapshot Config](ui.config.snapshot_config.de.md) | Welche Daten in den Markt-Snapshot fließen |
| [Decision Prompt](ui.config.decision_prompt.de.md) | System-Prompts für AA-Agenten |
| [Event Routing](ui.config.event_routing.de.md) | Event-Flow zwischen Modulen |
| [System Config](ui.config.system_config.de.md) | Globale System-Parameter |
| [LLM Modules](ui.config.llm_modules.de.md) | LLM-Provider-Verbindungen (Azure OpenAI / Anthropic) |
| [Broker Modules](ui.config.broker_modules.de.md) | Broker-Verbindungen (MT5 / OANDA) |

### Test
Werkzeuge zur Validierung der Konfiguration vor dem Live-Betrieb.

| Seite | Zweck |
|-------|-------|
| [LLM Checker](ui.test.llm_checker.de.md) | LLM-Konnektivität und Prompt-Antworten testen |
| [Tool Executor](ui.test.tool_executor.de.md) | System-Tools manuell aufrufen und Ausgaben prüfen |

---

## Systemarchitektur

OpenForexAI basiert auf einem zentralen **Event Bus**. Jedes Modul im System kommuniziert ausschließlich über diesen Bus — kein Modul ruft ein anderes direkt auf.

### Kernmodule

**Event Bus**
Das zentrale Nervensystem. Empfängt veröffentlichte Events und liefert sie an alle Abonnenten. Garantiert geordnete Zustellung innerhalb eines Topics. Alle Events werden im Event-Log persistiert.

**Broker-Adapter**
Verbindet sich mit MT5 oder OANDA. Aufgaben:
- Live-Kerzendaten für konfigurierte Paare streamen
- Market- und Limit-Orders ausführen
- Status offener Positionen abfragen
- Fills, Änderungen und Schließungen als Events melden

**AA-Agent (Analyse-Agent)**
Die KI-Reasoning-Engine. Für jedes abonnierte Paar und Zeitrahmen:
- Empfängt Kerzen-Close-Events
- Fordert Snapshot-Assembly von der Snapshot-Engine an
- Ruft das konfigurierte LLM mit dem assemblierten Snapshot und dem Decision Prompt auf
- Veröffentlicht Analyseergebnisse mit Signal, Konfidenz und Begründung

**Snapshot-Engine**
Stellt den Markt-Snapshot aus mehreren Datenquellen zusammen:
- Preis- und OHLCV-Daten
- ATR- und Volatilitätswerte
- Swing-Highs/-Lows (algorithmisch erkannt)
- Trendrichtung (EMA, Strukturanalyse)
- Session-Kontext (London/New York/Tokyo-Überschneidungen)
- Wirtschaftskalender-Events
- Benutzerdefinierte Calculation Blocks aus der Snapshot-Config

**EC Relay (Event Coordinator Relay)**
Die Regel-Engine zwischen Analyse und Ausführung:
- Empfängt Analysis-Complete-Events
- Wendet Zeit-, News- und Korrelationsfilter an
- Prüft Risikobudget (maximales offenes Risiko, maximale Trades je Paar)
- Leitet genehmigte Signale als Execution-Approved-Events weiter
- Veröffentlicht Signal-Rejected mit Grund, wenn blockiert

**BA-Agent (Broker Adapter Agent)**
Die Ausführungsschicht:
- Empfängt Execution-Approved-Events
- Berechnet präzise Entry-, Stop-Loss- und Take-Profit-Levels
- Platziert Orders über den Broker-Adapter
- Verwaltet den Positions-Lebenszyklus (Trailing Stops, Teilschließungen, Zeit-Exits)

**LLM-Adapter**
Abstrahiert den LLM-Provider:
- Unterstützt Azure OpenAI (GPT-4o, GPT-4o-mini) und Anthropic (Claude Sonnet, Claude Haiku)
- Behandelt Authentifizierung, Rate Limiting, Retry-Logik
- Formatiert Anfragen in providerspezifischen Schemas
- Gibt normalisierte Antworten unabhängig vom Provider zurück

**Monitor / Logger**
Persistiert alle Events und stellt der UI einen abfragbaren Event-Stream bereit. Unterstützt Filterung nach Event-Typ, Paar, Agent, Zeitbereich.

---

## Der Handels-Workflow

Der vollständige Handels-Workflow vom Kerzen-Close bis zur ausgeführten Order:

```
[Broker] ── candle_closed ──► [Event Bus]
                                    │
                            [AA-Agent abonniert]
                                    │
                            [Snapshot-Engine]
                            stellt Snapshot zusammen
                                    │
                            [LLM-Aufruf mit
                             Decision Prompt +
                             Snapshot als User-Msg]
                                    │
                            [LLM gibt Analyse zurück]
                            Signal + Konfidenz +
                            Entry + SL + TP +
                            Begründung
                                    │
                     analysis_complete ──► [Event Bus]
                                               │
                                       [EC Relay abonniert]
                                               │
                                       [Filter anwenden:
                                        Zeit / News /
                                        Risikobudget /
                                        Korrelation]
                                               │
                              ┌────────────────┴──────────────────┐
                          ABGELEHNT                           GENEHMIGT
                              │                                    │
                    signal_rejected                   execution_approved
                    ──► [Event Bus]                   ──► [Event Bus]
                    (geloggt, kein Trade)                      │
                                                     [BA-Agent abonniert]
                                                               │
                                                     [Präzise Entry/SL/TP
                                                      berechnen]
                                                               │
                                                     [Broker-Adapter
                                                      platziert Order]
                                                               │
                                                     order_placed
                                                     ──► [Event Bus]
```

### Signal bis Ausführung — typische Zeitspanne

Bei einem M5-Chart mit typischer LLM-Latenz:

- T+0:00 — Kerze schließt beim Broker
- T+0:01 — candle_closed-Event veröffentlicht
- T+0:02 — Snapshot-Assembly beginnt
- T+0:04 — Snapshot fertig, LLM-Aufruf initiiert
- T+0:08 — LLM-Antwort empfangen (variiert: 2–15 Sekunden)
- T+0:09 — EC Relay verarbeitet Signal
- T+0:10 — Order beim Broker platziert (wenn genehmigt)

Gesamtlatenz von Kerzen-Close bis Order: typischerweise 8–20 Sekunden je nach LLM-Antwortzeit.

---

## Strategie-Empfehlungen

### Was am meisten zählt

**1. Decision Prompt** (größter Einfluss)
Der System-Prompt, den das LLM erhält, ist der wirkungsvollste Hebel zur Anpassung des Handelsverhaltens. Ein gut ausgearbeiteter Prompt, der:
- die Strategie klar definiert (Trendfolge vs. Mean-Reversion vs. Breakout)
- Einstiegsbedingungen präzise spezifiziert
- das LLM anweist, wie widersprüchliche Indikatoren gewichtet werden sollen
- festlegt, was ein hoch- vs. niedrigkonfidentes Signal ausmacht

...wird einen generischen Prompt deutlich übertreffen. Vollständige Anleitung: [Decision Prompt Config](ui.config.decision_prompt.de.md).

**2. Snapshot Config** (großer Einfluss)
Die Daten, die das LLM erhält, bestimmen, worüber es argumentieren kann. Zu wenig → fehlender Kontext. Zu viel → Verwirrung oder hohe Kosten. Der Snapshot sollte genau die Daten enthalten, die deine Strategie benötigt. Siehe [Snapshot Config](ui.config.snapshot_config.de.md).

**3. EC Relay Filter** (mittlerer Einfluss)
Tageszeit-Filter und News-Sperrzeiträume können Fehlsignale deutlich reduzieren. Die meisten Trendstrategien performen schlecht bei geringer Liquidität (z. B. 22:00–01:00 UTC). Konfiguriere Event-Routing-Filter passend zum bevorzugten Handelsfenster deiner Strategie. Siehe [Event Routing](ui.config.event_routing.de.md).

**4. Risikoparameter** (kritisch für die Kapitalerhaltung)
Die Risiko-Einstellungen in Agent Config definieren die Positionsgröße. Der ATR-Multiplikator für den Stop-Loss und der Risikoprozentsatz pro Trade sind die primären Parameter. Konservative Einstellungen (0,5 % Risiko, 1,5x ATR Stop) liefern kleinere, aber nachhaltigere Ergebnisse.

**5. LLM-Modellauswahl** (Kosten vs. Qualität)
GPT-4o und Claude Sonnet liefern die höchste Analysequalität, sind aber teurer und langsamer. GPT-4o-mini und Claude Haiku sind schneller und günstiger, übersehen aber möglicherweise subtile Setups. Bei M5-Trading sollten die Kosten der LLM-Aufrufe pro Tag berücksichtigt werden. Siehe [LLM Modules](ui.config.llm_modules.de.md).

### Empfohlene Startkonfiguration

Für neue Nutzer wird folgende Startkonfiguration empfohlen:

- **Paare**: EURUSD, GBPUSD (liquide, gut verhaltend)
- **Zeitrahmen**: M5 (häufige Signale, überschaubare LLM-Kosten)
- **Risiko pro Trade**: 1 % des Kontos
- **Stop Loss**: 1,5x ATR
- **Take Profit**: 2,0x ATR (mindestens 1:1,33 R:R)
- **LLM**: GPT-4o-mini oder Claude Haiku zum Testen; auf Vollmodell upgraden, sobald die Strategie validiert ist
- **News-Filter**: Handel 30 Minuten vor und nach hochimpact-News sperren

### Strategie vor dem Live-Betrieb validieren

Nutze den [LLM Checker](ui.test.llm_checker.de.md), um zu prüfen, dass dein Decision Prompt konsistente, strukturierte Ausgaben liefert. Nutze den [Tool Executor](ui.test.tool_executor.de.md), um die korrekte Snapshot-Assembly zu verifizieren. Prüfe mehrere Tage Event-Logs im Monitor, bevor du die Live-Ausführung aktivierst.

---

## Sicherheitsrichtlinien

### Risikomanagement-Regeln

**Nie mehr als 3 % des Gesamtkontos über alle offenen Positionen riskieren.**
OpenForexAI erzwingt ein konfigurierbares Maximum an offenem Gesamtrisiko. Der Standardwert ist 3 %. Das bedeutet: Wenn drei Trades mit je 1 % Risiko offen sind, werden keine neuen Trades eingegangen, bis einer geschlossen wird. Dieser Wert ist in Agent Config konfigurierbar, sollte aber für Live-Trading niemals über 5 % erhöht werden.

**Stop-Loss muss immer gesetzt sein.**
Jeder Trade, den OpenForexAI platziert, enthält einen Stop-Loss-Level, der aus dem ATR (Average True Range) des Instruments berechnet wird. Der ATR-Stop stellt sicher, dass der Stop-Abstand proportional zur aktuellen Volatilität ist — weiter bei volatilen Sessions, enger bei ruhigen. Das System verweigert die Platzierung eines Trades, wenn kein gültiger Stop-Loss berechnet werden kann.

**ATR-basierte Positionsgröße verwenden.**
Keine fixen Lotgrößen verwenden. Der Positionsgrößen-Rechner verwendet die Formel:

```
Lots = (Kontokapital × Risiko%) / (Stop-Abstand in Pips × Pip-Wert)
```

Das stellt sicher, dass ein ausgestoppter Trade immer genau dem konfigurierten Risikoprozentsatz entspricht, unabhängig von Paar oder Volatilität.

**News-Risiko ist real.**
Wirtschaftliche Veröffentlichungen (NFP, CPI, Zinsentscheidungen) verursachen schnelle Preisbewegungen, die durch Stop-Losses hindurcgappen können. Nutze den News-Filter in Event Routing, um während dieser Zeitfenster den Handel zu sperren. Die Wirtschaftskalender-Daten sind im Snapshot für das LLM enthalten, aber der Hard-Block im EC Relay ist ein separater, regelbasierter Schutz.

**System in der ersten Woche beobachten.**
Auch mit allen Sicherheitsmaßnahmen können automatisierte Systeme bei ungewöhnlichen Marktbedingungen unerwartet reagieren. Beobachte den Monitor-Event-Stream täglich in der ersten Woche des Live-Betriebs. Prüfe, ob Signale vernünftig sind, kein einzelnes Paar eine übermäßige Anzahl an Trades erzeugt und das P&L den Erwartungen entspricht.

**Broker-API-Zugangsdaten sicher aufbewahren.**
Die Broker-Modul-Konfiguration enthält API-Schlüssel und Konto-Zugangsdaten. Niemals system.json5 oder Broker-Config-Dateien teilen. Umgebungsvariablen für sensible Werte verwenden, statt sie in Konfigurationsdateien hardzucodieren.

### Notfall-Stop

Wenn sich das System unerwartet verhält:

1. Den OpenForexAI-Prozess sofort stoppen
2. Direkt beim Broker einloggen und alle offenen Positionen prüfen
3. Positionen schließen, die nicht verstanden werden
4. Das Event-Log (Monitor) prüfen, um zu verstehen, was passiert ist
5. system.json5 und Agent Config auf Fehlkonfiguration prüfen, bevor neu gestartet wird

---

## Abschnittsindex

### Action-Bereich

- [Action Übersicht](ui.action.de.md) — Einführung in alle Action-Seiten
- [Initial Dashboard](ui.action.initial.de.md) — System-Status und Übersicht
- [Agent Chat](ui.action.chat.de.md) — Direkte LLM-Agenten-Interaktion
- [Orderbook](ui.action.orderbook.de.md) — Offene Positionen und Trade-Verlauf
- [Chart Analysis](ui.action.chart_analysis.de.md) — Visueller Chart mit KI-Overlay

### Monitor-Bereich

- [Event Stream](ui.monitor.de.md) — Echtzeit-Event-Feed

### Config-Bereich

- [Config Übersicht](ui.config.de.md) — Einführung in alle Config-Seiten
- [Agent Config](ui.config.agent_config.de.md) — Agenten-Definitionen und Risiko-Einstellungen
- [Entity Config](ui.config.entity_config.de.md) — Symbol- und Instrumenten-Konfiguration
- [Snapshot Config](ui.config.snapshot_config.de.md) — Markt-Snapshot-Assembly
- [Decision Prompt](ui.config.decision_prompt.de.md) — LLM-System-Prompts
- [Event Routing](ui.config.event_routing.de.md) — Signal-Filter und Event-Flow
- [System Config](ui.config.system_config.de.md) — Globale Parameter
- [LLM Modules](ui.config.llm_modules.de.md) — LLM-Provider-Einstellungen
- [Broker Modules](ui.config.broker_modules.de.md) — Broker-Verbindungs-Einstellungen

### Test-Bereich

- [Test Übersicht](ui.test.de.md) — Einführung in die Test-Tools
- [LLM Checker](ui.test.llm_checker.de.md) — LLM-Konnektivität und Prompts testen
- [Tool Executor](ui.test.tool_executor.de.md) — Manuelle Tool-Ausführung

---

*OpenForexAI Benutzerhandbuch — Deutsche Ausgabe*
*Für die englische Version dieses Handbuchs siehe [User Handbook](ui.en.md).*
