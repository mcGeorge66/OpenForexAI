[Zurück zu Config](ui.config.de.md)

# Event Routing

Event Routing ist das zentrale Nervensystem von OpenForexAI. Es steuert, wie jedes Ereignis jeder Komponente seine vorgesehenen Empfänger erreicht. Anstatt Kommunikationspfade fest im Agenten-Code zu verankern, verwendet das System eine deklarative Routing-Tabelle: eine Liste von Regeln, die der Event Bus zur Laufzeit auswertet, sobald eine Nachricht veröffentlicht wird. Dieses Design ermöglicht es, Datenflüsse hinzuzufügen, zu entfernen oder umzuleiten, ohne das System neu zu starten oder Agenten-Quellcode anzufassen.

Die Konfiguration wird in `config/RunTime/event_routing.json5` gespeichert und bei jeder Speicherung oder Löschung einer Regel sofort neu geladen.

---

## Inhaltsverzeichnis

1. [Was der Event Bus leistet](#was-der-event-bus-leistet)
2. [Die Routing-Tabelle](#die-routing-tabelle)
3. [Regel-Editor](#regel-editor)
4. [Ereignistyp-Referenz](#ereignistyp-referenz)
5. [From-Muster-Syntax](#from-muster-syntax)
6. [To-Ziel-Syntax](#to-ziel-syntax)
7. [Priorität](#priorität)
8. [Regeln deaktivieren](#regeln-deaktivieren)
9. [Live-Regel-Erklärungspanel](#live-regel-erklärungspanel)
10. [Schaltflächen und Aktionen](#schaltflächen-und-aktionen)
11. [Die vollständige Routing-Kette](#die-vollständige-routing-kette)
12. [Praktische Beispiele](#praktische-beispiele)
13. [Routing-Probleme beheben](#routing-probleme-beheben)
14. [Designprinzipien](#designprinzipien)

---

## Was der Event Bus leistet

Der Event Bus ist ein Publish-Subscribe-Nachrichtenbroker, der innerhalb des OpenForexAI-Prozesses läuft. Jede Komponente — Agenten, Datengateways, Broker-Adapter, LLM-Dienste, das Repository — registriert sich als Bus-Mitglied mit einer eindeutigen Agent-ID. Wenn eine Komponente kommunizieren möchte, veröffentlicht sie ein Ereignis auf dem Bus. Der Bus wertet daraufhin alle Routing-Regeln in Prioritätsreihenfolge aus und liefert das Ereignis an jeden Empfänger, der von einer Regel abgedeckt wird.

Kerneigenschaften:

- **Entkoppelt**: Publisher wissen nicht, wer ihre Ereignisse empfängt.
- **Zur Laufzeit konfigurierbar**: Regeln können während des Betriebs hinzugefügt, geändert oder gelöscht werden.
- **Priorisiert**: Bei mehreren übereinstimmenden Regeln werden niedrigere Prioritätsnummern zuerst verarbeitet.
- **Gefiltert**: Jede Regel gibt an, welche Ereignistypen und welche Absender sie betrifft.
- **Hot-Reload**: Das Klicken auf „Update" oder „Delete" löst eine sofortige Neuladung der Routing-Konfiguration aus — kein Neustart erforderlich.

Der Bus puffert nicht zugestellte Ereignisse nicht. Wenn ein Ziel bei einem Zustellversuch nicht registriert ist, wird das Ereignis verworfen und ein Warneintrag ins Log geschrieben.

---

## Die Routing-Tabelle

Die Routing-Tabelle wird als sortierbare, filterbare Tabelle angezeigt. Jede Zeile stellt eine Routing-Regel dar.

### Spalten

| # | Spalte | Beschreibung |
|---|--------|--------------|
| 1 | **#** | Zeilennummer (nur Anzeige) |
| 2 | **Id** | Eindeutiger snake_case-Regelbezeichner |
| 3 | **Event** | Der Ereignistyp, auf den diese Regel passt |
| 4 | **From** | Absender-Muster (Agent-ID-Format oder Wildcard) |
| 5 | **To** | Ziel-Ausdruck (literal, Wildcard oder Template) |
| 6 | **Prio** | Prioritätsnummer (1 = höchste, 200 = niedrig) |
| 7 | **Off** | Oranges `●` wenn die Regel deaktiviert ist |

### Sortierung

Klick auf eine Spaltenüberschrift sortiert aufsteigend. Erneuter Klick sortiert absteigend. Der Sortierindikator (▲ oder ▼) erscheint in der aktiven Überschrift. Die Sortierung beeinflusst die Auswertungsreihenfolge der Regeln nicht — diese wird immer durch das Prioritätsfeld bestimmt, unabhängig von der Anzeigereihenfolge.

### Filterung

Vier Filtereingabefelder befinden sich über der Tabelle:

- **Id-Filter**: Teilstring-Abgleich auf die Regel-ID
- **Event-Filter**: Teilstring-Abgleich auf den Ereignistyp
- **From-Filter**: Teilstring-Abgleich auf das From-Muster
- **To-Filter**: Teilstring-Abgleich auf den To-Ausdruck

Alle Filter werden gleichzeitig angewendet (UND-Logik). Filter löschen durch Leeren des Textfeldes. Filter sind nicht zwischen Groß- und Kleinschreibung unterscheidend.

### Zeilenauswahl

Klick auf eine Zeile wählt sie aus. Die gewählte Zeile wird hervorgehoben und ihre Werte in den Regel-Editor unten geladen. Das Bearbeiten von Feldern im Regel-Editor ändert die Regel nicht, bis auf **Update** oder **Save As New** geklickt wird.

---

## Regel-Editor

Der Regel-Editor befindet sich im unteren linken Bereich des Event-Routing-Bildschirms.

### ID

Ein eindeutiger snake_case-Bezeichner für diese Regel. Beispiele: `aa_to_ec_relay`, `ec_to_ba`, `candles_request_to_data`, `order_request_to_broker`.

Regeln:
- Muss unter allen Routing-Regeln eindeutig sein
- Nur Kleinbuchstaben, Ziffern und Unterstriche verwenden
- Sollte den Zweck der Route beschreiben
- Kann für eine bestehende Regel nicht über Update geändert werden — Delete und anschließend Save As New verwenden

### Event

Ein Dropdown mit allen bekannten Ereignistypen, nach Kategorie gruppiert. Den Ereignistyp auswählen, auf den diese Regel passen soll. Der Sonderwert `*` bedeutet, dass die Regel auf alle Ereignistypen unabhängig vom Inhalt passt.

### Description

Ein optionales Freitextfeld für menschenlesbare Anmerkungen. Dieser Text erscheint im Live-Regel-Erklärungspanel als „Was"-Beschreibung des Ereignisses.

### From

Das Absender-Muster. Steuert, welche publizierende(n) Komponente(n) diese Regel betrifft. Verwendet die Agent-ID-Segmentsyntax. Siehe Abschnitt From-Muster-Syntax.

### To

Der Ziel-Ausdruck. Steuert, wohin übereinstimmende Ereignisse geliefert werden. Unterstützt literale IDs, Wildcards und Templates. Siehe Abschnitt To-Ziel-Syntax.

### Priority

Eine ganze Zahl zwischen 1 und 200. Niedrigere Zahlen werden zuerst verarbeitet, wenn mehrere Regeln dasselbe Ereignis treffen.

### Disable

Eine Checkbox. Wenn aktiviert, bleibt die Regel in der Konfiguration, wird aber bei der Routing-Auswertung übersprungen. Die Zeile zeigt ein oranges `●` in der Off-Spalte.

---

## Ereignistyp-Referenz

Ereignisse sind nach funktionaler Kategorie gruppiert.

### Marktereignisse

| Ereignis | Beschreibung | Gesendet von |
|----------|--------------|--------------|
| `m5_agent_trigger` | Feuert bei jedem M5-Kerzenschluss; signalisiert AA-Agenten den Analysebeginn | AD-Agent (AgentDispatcher) |
| `m5_candle_update` | Echtzeit-Tick-Kerzen-Update (noch nicht geschlossen) | Broker-Adapter |
| `m5_candle_saved` | Bestätigung, dass eine geschlossene M5-Kerze in der Datenbank gespeichert wurde | Data Gateway |
| `candle_gap_detected` | Meldet, dass während der Synchronisierung eine Lücke in der Kerzenhistorie gefunden wurde | Data Gateway |

### Indikatorereignisse

| Ereignis | Beschreibung | Gesendet von |
|----------|--------------|--------------|
| `candles_request` | Anfrage nach historischen Kerzen für ein bestimmtes Paar/Zeitrahmen/Anzahl | AA-Agent oder andere Anfragende |
| `candles_response` | Erfüllung einer candles_request mit OHLCV-Daten | GA-DATA (Daten-Gateway) |
| `indicator_request` | Anfrage zur Berechnung eines technischen Indikators (EMA, RSI, ATR usw.) | AA-Agent |
| `indicator_response` | Berechnete Indikatorwerte, bereit für die Snapshot-Zusammenstellung | GA-DATA |
| `swing_levels_request` | Anfrage nach Swing-Hoch/Tief-Niveaus für ein Paar/Zeitrahmen/Lookback | AA-Agent |
| `swing_levels_response` | Berechnete Swing-Niveaus mit Preis und Zeitstempel | GA-DATA |

### Kontoereignisse

| Ereignis | Beschreibung | Gesendet von |
|----------|--------------|--------------|
| `account_status_request` | Anfrage nach aktuellem Kontostand, Eigenkapital, Margin | BA-Agent oder UI |
| `account_status_response` | Aktueller finanzieller Kontozustand | Broker-Adapter |
| `account_status_updated` | Proaktiver Push bei signifikanten Kontozustandsänderungen | Broker-Adapter |
| `positions_request` | Anfrage nach Liste der aktuell offenen Positionen | BA-Agent |
| `positions_response` | Offene Positionen mit Symbol, Richtung, Größe, G&V | Broker-Adapter |

### Handelsereignisse

| Ereignis | Beschreibung | Gesendet von |
|----------|--------------|--------------|
| `order_request` | Anweisung zur Platzierung einer neuen Market- oder Pending-Order | BA-Agent |
| `order_result` | Ergebnis einer order_request (Erfolg/Fehler, Ticket-ID) | Broker-Adapter |
| `position_close_request` | Anweisung zum Schließen einer bestimmten offenen Position | BA-Agent |
| `position_close_result` | Ergebnis einer Close-Anfrage | Broker-Adapter |
| `order_modify_request` | Anfrage zur Änderung von SL/TP einer bestehenden Position | BA-Agent |
| `order_modify_result` | Ergebnis einer Modify-Anfrage | Broker-Adapter |
| `signal_generated` | AA-Agent hat eine Handelssignalempfehlung erstellt | AA-Agent |
| `signal_approved` | EC-Entität hat ein Signal zur Ausführung genehmigt | EC-Entität |
| `signal_rejected` | EC-Entität hat ein Signal abgelehnt | EC-Entität |
| `order_placed` | Bestätigung, dass eine Order beim Broker eingereicht wurde | BA-Agent |
| `position_opened` | Eine neue Position ist jetzt im Broker-Konto aktiv | Broker-Adapter |
| `position_closed` | Eine Position wurde vollständig geschlossen | Broker-Adapter |

### Analyseereignisse

| Ereignis | Beschreibung | Gesendet von |
|----------|--------------|--------------|
| `analysis_requested` | Manueller oder geplanter Auftrag für einen AA-Agenten zur Durchführung einer Analyse | UI oder Scheduler |
| `analysis_result` | Ausgabe der AA-Agenten-Analyse einschließlich Signal und Snapshot | AA-Agent |

### Agentenereignisse

| Ereignis | Beschreibung | Gesendet von |
|----------|--------------|--------------|
| `agent_query` | Allgemeine Anfrage an einen bestimmten Agenten | Beliebige Komponente |
| `agent_response` | Antwort auf eine agent_query | Ziel-Agent |
| `agent_config_requested` | Anfrage nach der aktuellen Konfiguration eines Agenten | UI-Konfig-Panel |
| `agent_config_response` | Agent gibt seine aktuelle Konfigurations-JSON zurück | Agent |
| `agent_trigger_received` | Agent bestätigt den Empfang eines Triggers | AA-Agent |
| `agent_trigger_skipped` | Agent hat einen Trigger übersprungen (außerhalb der Session, keine Positionen usw.) | AA-Agent |

### EC-Ereignisse

| Ereignis | Beschreibung | Gesendet von |
|----------|--------------|--------------|
| `ec_config_requested` | Anfrage nach der aktuellen Konfiguration einer EC-Entität | UI-Konfig-Panel |
| `ec_config_response` | EC-Entität gibt ihre Konfiguration zurück | EC-Entität |
| `ec_output` | Entscheidungsausgabe der EC-Entität (Signal genehmigt/abgelehnt + Sizing) | EC-Entität |

### LLM-Ereignisse

| Ereignis | Beschreibung | Gesendet von |
|----------|--------------|--------------|
| `llm_request` | Anfrage zum Aufruf eines LLM mit System-Prompt und Benutzernachricht | AA-Agent |
| `llm_response` | Antwort des LLM einschließlich Rohtext und geparster Entscheidung | LLM-Servicemodul |

### Repository-Ereignisse

| Ereignis | Beschreibung | Gesendet von |
|----------|--------------|--------------|
| `repo_request` | Anfrage zum Lesen oder Schreiben von Daten im Repository (Entscheidungen, Snapshots) | Beliebige Komponente |
| `repo_response` | Ergebnis einer repo_request | GA-REPO (Repository-Gateway) |

### Systemereignisse

| Ereignis | Beschreibung | Gesendet von |
|----------|--------------|--------------|
| `routing_reload_requested` | Löst ein sofortiges Neulesen der Routing-Konfiguration aus | Konfig-UI |
| `prompt_updated` | Signalisiert, dass eine Prompt-Vorlage geändert wurde | Prompt-Konfig-UI |
| `system_info` | Allgemeine Informationssystemmeldung | Beliebige Komponente |
| `system_error` | Systemfehlerbenachrichtigung | Beliebige Komponente |
| `*` | Wildcard — passt auf jeden Ereignistyp | (nur in Regeln verwendet) |

---

## From-Muster-Syntax

Das From-Feld verwendet das Agent-ID-Segmentformat. Eine Agent-ID hat vier durch Bindestriche getrennte Segmente:

```
{BROKER}-{PAIR}-{TYP}-{ROLLE}
```

Beispiele für echte Agent-IDs:
- `OXS_T-EURUSD-AA-ANLYS` — der Analyse-Agent für EURUSD bei Broker OXS_T
- `SYSTM-ALL___-GA-DATA` — das globale Daten-Gateway
- `OXS_T-ALL___-BA-ANLYS` — der BA-Agent für Broker OXS_T
- `OXS_T-EURUSD-EC-RELAY` — die EC-Entität für EURUSD bei OXS_T
- `OXS_T-ALL___-AD-DISP` — der AgentDispatcher für OXS_T

### Wildcard-Segmente

`*` verwenden, um einen beliebigen Wert in einem Segment abzugleichen:

| Muster | Passt auf |
|--------|-----------|
| `*` | Beliebiger Absender (alle Komponenten) |
| `*-*-AA-*` | Alle AA-Agenten, beliebiger Broker, beliebiges Paar |
| `*-*-EC-*` | Alle EC-Entitäten, beliebiger Broker, beliebiges Paar |
| `*-*-AD-*` | Alle AgentDispatcher-Agenten |
| `*-*-BA-*` | Alle BA-Agenten, beliebiger Broker |
| `OXS_T-*-AA-*` | Alle AA-Agenten bei Broker OXS_T |
| `OXS_T-EURUSD-AA-ANLYS` | Exakter Abgleich — nur dieser eine Agent |
| `*-*-GA-*` | Alle Gateway-Agenten |

Wildcard-Abgleich erfolgt segmentweise. Ein `*` in einem Segment gleicht nicht über Bindestriche hinweg ab.

### Spezielle Broker-/Paar-Werte

- `SYSTM` — Systemkomponenten (Gateways, Config-Service, Repository)
- `ALL___` — verwendet, wenn eine Komponente nicht paarspezifisch ist (6 Zeichen mit nachgestellten Unterstrichen). Beispiel: `OXS_T-ALL___-BA-ANLYS` ist der BA-Agent für den gesamten OXS_T-Broker.

---

## To-Ziel-Syntax

Das To-Feld bestimmt, wohin übereinstimmende Ereignisse geliefert werden. Drei Formen werden unterstützt:

### 1. Literale ID

An genau ein registriertes Bus-Mitglied liefern:

```
OXS_T-ALL___-BA-ANLYS
SYSTM-ALL___-GA-DATA
SYSTM-ALL___-GA-REPO
SYSTM-ALL___-GA-CFGSV
```

Das Ziel muss ein aktuell registriertes Bus-Mitglied sein. Wenn das Mitglied nicht registriert ist, wird das Ereignis mit einer Warnung im Log verworfen.

### 2. Wildcard

An alle registrierten Bus-Mitglieder liefern, deren IDs dem Muster entsprechen:

```
*-*-EC-*         → alle EC-Entitäten
*-*-AA-*         → alle AA-Agenten
*                → Broadcast an jedes registrierte Bus-Mitglied
```

Wildcard-Zustellung sendet eine Kopie an jedes übereinstimmende Mitglied.

### 3. Template

Die Ziel-ID dynamisch aus der Absender-ID ableiten. Verwendet `{sender.segment}`-Platzhalter:

| Platzhalter | Wert |
|-------------|------|
| `{sender.broker}` | Erstes Segment der Absender-ID (z.B. `OXS_T`) |
| `{sender.pair}` | Zweites Segment der Absender-ID (z.B. `EURUSD`) |
| `{sender.type}` | Drittes Segment der Absender-ID (z.B. `AA`) |
| `{sender.role}` | Viertes Segment der Absender-ID (z.B. `ANLYS`) |

Template-Beispiele und ihre Auflösung:

```
{sender.broker}-{sender.pair}-EC-RELAY
```
Absender `OXS_T-EURUSD-AA-ANLYS` → ergibt `OXS_T-EURUSD-EC-RELAY`

```
{sender.broker}-ALL___-BA-ANLYS
```
Absender `OXS_T-EURUSD-EC-RELAY` → ergibt `OXS_T-ALL___-BA-ANLYS`

Templates ermöglichen es, mit einer einzigen Regel Events von beliebig vielen Broker/Paar-Kombinationen korrekt zu routen.

---

## Priorität

Priorität ist eine ganze Zahl von 1 bis 200. Der Event Bus verarbeitet übereinstimmende Regeln in aufsteigender Prioritätsreihenfolge (1 zuerst, 200 zuletzt).

Empfohlene Prioritätsbereiche:

| Bereich | Verwendung |
|---------|------------|
| 1–10 | Kritische Systemrouten (Konfigurationsanfragen, Fehlerbehandlung) |
| 11–30 | Kern-Datenfluss (Kerzen-, Indikator-, Repo-Anfragen) |
| 31–60 | Agenten-Trigger-Routing und Analysefluss |
| 61–100 | EC- und BA-Routing, Order-Verarbeitung |
| 101–150 | Monitoring, Logging, UI-Benachrichtigungsrouten |
| 151–200 | Optionale, niedrigpriorisierte oder experimentelle Routen |

---

## Regeln deaktivieren

Regeln können deaktiviert werden, ohne sie zu löschen. Eine deaktivierte Regel:
- Wird in der Konfigurationsdatei gespeichert
- Wird in der Routing-Tabelle mit einem orangen `●` in der Off-Spalte angezeigt
- Wird bei der Routing-Auswertung vollständig übersprungen
- Kann jederzeit durch Bearbeiten und Deaktivieren der Disable-Option reaktiviert werden

Anwendungsfälle:
- Temporäres Stoppen eines Datenflusses während der Fehlerbehebung
- Pausieren der Analyse eines Paares ohne Entfernen der Konfiguration
- A/B-Tests alternativer Routing-Konfigurationen
- Vorbereiten eines neuen Regelsets vor der Aktivierung

---

## Live-Regel-Erklärungspanel

Das Live-Regel-Erklärungspanel befindet sich im unteren rechten Bereich des Event-Routing-Bildschirms. Es aktualisiert sich in Echtzeit beim Bearbeiten der Regel-Editor-Felder.

### Zusammenfassung in natürlicher Sprache

Oben im Panel: Ein einfacher deutschsprachiger Satz, der beschreibt, was die aktuelle Regel bewirkt.

Beispiel:
> "Wenn `analysis_result` von einem beliebigen AA-Agenten gesendet wird, wird es mit Priorität 40 an die EC-RELAY-Entität für denselben Broker und dasselbe Paar zugestellt."

### EVENT-Bereich

- **Typ**: Der Ereignisname mit seiner Kategorie-Farbcodierung
- **Was**: Der Wert des Description-Feldes oder eine automatisch generierte Beschreibung
- **Gesendet von**: Welcher Komponententyp dieses Ereignis normalerweise erzeugt

### FROM-Bereich

- **Muster**: Der rohe From-Wert
- **Erklärung**: Menschenlesbare Interpretation des Musters

### TO-Bereich

- **Ziel**: Der rohe To-Wert
- **Erklärung**: Menschenlesbare Interpretation mit aufgelöstem Beispiel

### VALIDIERUNG-Bereich

| Problem | Schwere |
|---------|---------|
| Doppelte ID | Fehler — blockiert Speichern |
| Leere ID | Fehler — blockiert Speichern |
| Ungültiges ID-Format (Leerzeichen, Großbuchstaben) | Fehler — blockiert Speichern |
| Leeres Event | Fehler — blockiert Speichern |
| Leeres From | Fehler — blockiert Speichern |
| Leeres To | Fehler — blockiert Speichern |
| Priorität keine Zahl 1–200 | Fehler — blockiert Speichern |
| Unbekannter Ereignistyp | Warnung — Speichern möglich |

---

## Schaltflächen und Aktionen

| Schaltfläche | Farbe | Aktion |
|--------------|-------|--------|
| **New Empty Rule** | Amber | Alle Formularfelder leeren für eine neue Regel |
| **Update** | Grün | Änderungen an der gewählten Regel speichern und Hot-Reload auslösen |
| **Save As New** | Blau | Neue Regel mit den aktuellen Formularwerten erstellen (ID muss eindeutig sein) |
| **Delete** | Rot | Gewählte Regel entfernen und Hot-Reload auslösen |

Hot-Reload bedeutet, dass der Event Bus die aktualisierte Routing-Konfiguration sofort anwendet. Kein Neustart erforderlich, keine Unterbrechung für laufende Agenten.

---

## Die vollständige Routing-Kette

Nachfolgend alle Standard-Routing-Regeln einer Standard-OpenForexAI-Installation in logischer Ablaufreihenfolge.

---

### Regel 1: `agent_config_request_to_cfgsv`

| Feld | Wert |
|------|------|
| Event | `agent_config_requested` |
| From | `*` |
| To | `SYSTM-ALL___-GA-CFGSV` |
| Priority | 5 |

**Zweck**: Wenn eine Komponente Agenten-Konfigurationsdaten anfordert (typischerweise das UI-Konfig-Panel), wird die Anfrage an den Konfigurationsservice-Gateway geleitet. Der Config-Service liest die aktuelle Konfiguration von der Festplatte und gibt eine `agent_config_response` zurück.

---

### Regel 2: `ec_config_request_to_cfgsv`

| Feld | Wert |
|------|------|
| Event | `ec_config_requested` |
| From | `*-*-EC-*` |
| To | `SYSTM-ALL___-GA-CFGSV` |
| Priority | 5 |

**Zweck**: EC-Entitäten, die ihre eigene Konfiguration anfordern, werden an den Config-Service geleitet. Dies ermöglicht EC-Entitäten, ihre Regeln, Schwellenwerte und Gate-Parameter zur Laufzeit neu zu laden.

---

### Regel 3: `ad_trigger_to_aa`

| Feld | Wert |
|------|------|
| Event | `m5_agent_trigger` |
| From | `*-*-AD-*` |
| To | `{sender.broker}-{sender.pair}-AA-ANLYS` |
| Priority | 20 |

**Zweck**: Der AgentDispatcher feuert bei jedem M5-Kerzenschluss einen `m5_agent_trigger` für jedes aktive Paar. Das Template leitet jeden Trigger an den AA-Analyse-Agenten für denselben Broker und dasselbe Paar. Feuert der AD für `OXS_T-EURUSD-AD-DISP`, geht das Ereignis an `OXS_T-EURUSD-AA-ANLYS`.

**Template-Vorteil**: Deckt alle Paare automatisch ab. Das Hinzufügen eines neuen Paares erfordert keine neue Routing-Regel.

---

### Regel 4: `aa_result_to_ec`

| Feld | Wert |
|------|------|
| Event | `analysis_result` |
| From | `*-*-AA-*` |
| To | `{sender.broker}-{sender.pair}-EC-RELAY` |
| Priority | 40 |

**Zweck**: Nachdem der AA-Agent die Analyse abgeschlossen und ein `analysis_result` erstellt hat, wird das Ergebnis an den Event Composer (EC) für diesen Broker/dieses Paar geleitet. Der EC wertet Gate-Bedingungen aus, reichert das Ergebnis mit Risk-Sizing an und entscheidet, ob das Signal genehmigt oder abgelehnt wird.

---

### Regel 5: `ec_output_to_ba`

| Feld | Wert |
|------|------|
| Event | `ec_output` |
| From | `*-*-EC-*` |
| To | `{sender.broker}-ALL___-BA-ANLYS` |
| Priority | 50 |

**Zweck**: Die Entscheidungsausgabe der EC-Entität (genehmigtes/abgelehntes Signal mit Positionsgröße) wird an den Broker-Agenten für denselben Broker weitergeleitet. Beachte `ALL___` im To-Ziel — BA-Agenten sind nicht paarspezifisch; ein BA-Agent behandelt alle Paare für einen bestimmten Broker.

---

### Regel 6: `candles_request_to_data`

| Feld | Wert |
|------|------|
| Event | `candles_request` |
| From | `*` |
| To | `SYSTM-ALL___-GA-DATA` |
| Priority | 30 |

**Zweck**: Jede Komponente, die historische Kerzendaten anfordert, wird an den Data Gateway weitergeleitet. Das Data Gateway fragt die Datenbank ab oder fordert vom Broker-Adapter an und gibt dann eine `candles_response` zurück.

---

### Regel 7: `indicator_request_to_data`

| Feld | Wert |
|------|------|
| Event | `indicator_request` |
| From | `*` |
| To | `SYSTM-ALL___-GA-DATA` |
| Priority | 30 |

**Zweck**: Indikatorberechnungsanfragen (EMA, RSI, ATR) werden an das Data Gateway weitergeleitet, das die Berechnung mit den gespeicherten Kerzendaten durchführt und eine `indicator_response` zurückgibt.

---

### Regel 8: `swing_levels_request_to_data`

| Feld | Wert |
|------|------|
| Event | `swing_levels_request` |
| From | `*` |
| To | `SYSTM-ALL___-GA-DATA` |
| Priority | 30 |

**Zweck**: Swing-Level-Anfragen werden an das Data Gateway weitergeleitet. Gibt `swing_levels_response` mit erkannten Pivot-Hoch/Tief-Niveaus und ihren Zeitstempeln zurück.

---

### Regel 9: `repo_request_to_repo`

| Feld | Wert |
|------|------|
| Event | `repo_request` |
| From | `*` |
| To | `SYSTM-ALL___-GA-REPO` |
| Priority | 25 |

**Zweck**: Alle Repository-Lese-/Schreibanfragen (Entscheidungen, Snapshots, Handelshistorie) werden an den Repository-Gateway weitergeleitet.

---

### Regel 10: `order_request_to_broker`

| Feld | Wert |
|------|------|
| Event | `order_request` |
| From | `*-*-BA-*` |
| To | `{sender.broker}-ALL___-BK-CONN` |
| Priority | 60 |

**Zweck**: Order-Platzierungsanfragen von BA-Agenten werden an den Broker-Connector für denselben Broker weitergeleitet.

---

### Regel 11: `account_status_request_to_broker`

| Feld | Wert |
|------|------|
| Event | `account_status_request` |
| From | `*` |
| To | `{sender.broker}-ALL___-BK-CONN` |
| Priority | 35 |

**Zweck**: Kontostatusanfragen werden an den entsprechenden Broker-Connector weitergeleitet.

---

## Praktische Beispiele

### Beispiel A: Routing für ein neues Paar einrichten

Du fügst GBPUSD-Handel bei Broker OXS_T hinzu. Überprüfe, ob diese drei Regeln mit Templates (nicht hartkodierten Paaren) existieren:

1. `ad_trigger_to_aa` — From: `*-*-AD-*`, To: `{sender.broker}-{sender.pair}-AA-ANLYS`
2. `aa_result_to_ec` — From: `*-*-AA-*`, To: `{sender.broker}-{sender.pair}-EC-RELAY`
3. `ec_output_to_ba` — From: `*-*-EC-*`, To: `{sender.broker}-ALL___-BA-ANLYS`

Wenn alle drei Templates verwenden, wird GBPUSD automatisch unterstützt. Keine neuen Routing-Regeln erforderlich.

---

### Beispiel B: Monitoring-Route hinzufügen

Du möchtest jedes `analysis_result` an einen Monitoring-Agenten `SYSTM-ALL___-MN-LOG` senden:

| Feld | Wert |
|------|------|
| ID | `analysis_result_to_monitor` |
| Event | `analysis_result` |
| From | `*` |
| To | `SYSTM-ALL___-MN-LOG` |
| Priority | 150 |
| Description | Alle Analyseergebnisse an Monitoring-Logger senden |

---

### Beispiel C: Fehlendes Signal debuggen

Signale vom EURUSD-AA-Agenten erreichen den BA-Agenten nicht. Systematische Checkliste:

1. Event Routing öffnen, `Event = analysis_result` filtern — Regel `aa_result_to_ec` vorhanden und nicht deaktiviert?
2. To-Template prüfen: `{sender.broker}-{sender.pair}-EC-RELAY` — ist `OXS_T-EURUSD-EC-RELAY` im System Monitor als registriertes Mitglied sichtbar?
3. `Event = ec_output` filtern — Regel `ec_output_to_ba` vorhanden?
4. Priorität prüfen — gibt es andere Regeln mit niedrigerer Zahl, die `analysis_result` abfangen?
5. Log auf folgende Meldungen prüfen:
   - `[BUS] No rule matched for event analysis_result from OXS_T-EURUSD-AA-ANLYS`
   - `[BUS] Target OXS_T-EURUSD-EC-RELAY not registered`

---

## Routing-Probleme beheben

### Symptom: Ereignisse werden veröffentlicht, aber nie empfangen

1. Regel ist deaktiviert (Off-Spalte prüfen)
2. Ziel-ID im To-Feld stimmt mit keinem registrierten Bus-Mitglied überein
3. From-Muster passt nicht auf die tatsächliche Absender-ID (Log auf exakte Absender-ID prüfen)
4. Prioritätskonflikt mit einer blockierenden Regel

### Symptom: Ereignis von falscher Komponente empfangen

1. Zwei Regeln passen auf dieselbe Event/From-Kombination mit überlappenden To-Mustern
2. Template wurde auf unerwarteten Wert aufgelöst — DEBUG-Logging aktivieren
3. Wildcard in To ist zu breit

### Symptom: Routing-Änderung hat keine Wirkung

1. Auf Update vs. Save As New geklickt — Update ändert bestehende, Save As New erstellt Duplikat
2. Syntaxfehler in Muster — Validierungspanel prüfen
3. Hot-Reload fehlgeschlagen — Log auf `[BUS] Routing reload failed` prüfen

### Log-Meldungen für Routing

| Log-Meldung | Bedeutung |
|-------------|-----------|
| `[BUS] No rule matched for event X from Y` | Keine Routing-Regel anwendbar — Ereignis verworfen |
| `[BUS] Target Z not registered` | Regel passt, aber Ziel nicht im Bus |
| `[BUS] Routing reloaded (N rules)` | Hot-Reload erfolgreich abgeschlossen |
| `[BUS] Routing reload failed: <error>` | Syntax- oder Validierungsfehler in Konfig |
| `[BUS] Delivered X from Y to Z` | Debug-Bestätigung der erfolgreichen Zustellung |

---

## Designprinzipien

### Warum eine Routing-Tabelle statt hartcodierter Pfade

Hartcodiertes Routing koppelt Komponenten eng aneinander. Das Hinzufügen eines neuen Paares würde Code-Änderungen im AgentDispatcher, dem AA-Agenten, der EC-Entität und dem BA-Agenten erfordern. Mit Routing-Tabellen ist das Hinzufügen eines Paares eine reine Konfigurationsaufgabe.

### Warum Templates

Templates verhindern eine kombinatorische Explosion von Regeln. Ohne Templates: 5 Broker × 20 Paare = 100 Regeln nur für den AA→EC-Link. Mit dem Template `{sender.broker}-{sender.pair}-EC-RELAY` deckt eine einzige Regel alle 100 Kombinationen automatisch ab.

### Warum Prioritätsnummern statt Regelreihenfolge

Regelreihenfolge in einer Datei ist fragil — das Einfügen einer Regel ändert alle nachfolgenden Indizes. Prioritätsnummern entkoppeln logische Wichtigkeit von physischer Position.

### Warum Hot-Reload

Märkte hören nicht auf. Die Möglichkeit, Routing zu korrigieren oder anzupassen, ohne das gesamte System neu zu starten, ist in einer Live-Handelsumgebung unerlässlich.

---

*Dieses Dokument behandelt Event Routing in OpenForexAI v0.7+. Für die Agenten-Konfiguration siehe [Agent Config](ui.config.agent_config.de.md). Für EC-Entitätskonfiguration siehe [Entity Config](ui.config.entity_config.de.md).*
