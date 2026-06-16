[Zurück zu Config](ui.config.de.md)

# Agent Config

`Agent Config` ist das zentrale Werkzeug, um einzelne Agenten anzulegen, zu konfigurieren und zu verwalten. Alle Einstellungen werden direkt in der Datei `config/system.json5` gespeichert. Änderungen werden erst wirksam, wenn der Agentenprozess neu gestartet oder der Agent per Trigger neu geladen wird.

---

## Aufbau der Oberfläche

Die Seite besteht aus drei Bereichen:

- **Agent Selection** — Auswahl des zu bearbeitenden Agenten
- **Agent Editor** — alle Felder zur Konfiguration
- **Sidebar** — Live-Vorschau der aktuellen Konfiguration und Validierungsfehler

---

## Agent Selection

Das Dropdown oben zeigt alle im System vorhandenen Agenten. Jeder Eintrag zeigt `Agent-ID | Typ | Status | LLM | Broker`. Nach Auswahl eines Agenten werden alle Felder mit dessen aktuellen Werten befüllt.

---

## Aktionsschaltflächen

| Schaltfläche | Farbe | Funktion |
|---|---|---|
| **New Empty Agent** | Amber | Leert alle Felder für einen neuen Agenten — speichert noch nichts |
| **Update** | Grün | Überschreibt den aktuell ausgewählten Agenten in der Config |
| **Save As New** | Blau | Legt einen neuen Agenten mit der aktuellen Agent-ID an — schlägt fehl, wenn die ID bereits existiert |
| **Delete** | Rot | Löscht den aktuell ausgewählten Agenten aus der Config |

> **Hinweis:** `Update` und `Delete` wirken auf den zuletzt aus dem Dropdown ausgewählten Agenten, nicht zwangsläufig auf die im Feld eingetragene Agent-ID.

---

## Felder im Agent Editor

### Agent ID

**Format:** `BROKER(5)-PAIR(6)-TYP(2)-NAME(1–5)`, z. B. `OAPR1-EURUSD-AA-ANLYS`

- **BROKER** — 5-stelliges Kürzel des Brokers, z. B. `OAPR1`
- **PAIR** — 6-stelliges Währungspaar, z. B. `EURUSD` oder `ALL___`
- **TYP** — 2-stelliger Typ-Code (siehe Feld *Type*)
- **NAME** — 1–5-stellige Kurzbezeichnung, z. B. `ANLYS`, `EXEC`, `MON`

Die ID wird automatisch in Großbuchstaben umgewandelt. Sie dient als eindeutiger Schlüssel für Routing und Start — keine zwei Agenten dürfen dieselbe ID haben. Pflichtfeld, Validierung schlägt fehl wenn das Format nicht stimmt.

---

### Enable

`true` — Der Agent wird beim Start geladen und empfängt Ereignisse.  
`false` — Die Konfiguration bleibt gespeichert, der Agent ist jedoch inaktiv und wird nicht gestartet.

Verwendung: Agenten können damit temporär deaktiviert werden, ohne die Konfiguration zu löschen.

---

### Pass Trigger

Steuert, ob der **Inhalt** des auslösenden Ereignisses als User-Message an das LLM übergeben wird.

`false` (Standard) — Das LLM bekommt eine leere User-Message. Der Agent läuft zwar, hat aber keinen Zugriff auf den Ereignisinhalt — er arbeitet ausschließlich auf Basis seines System Prompts und eigener Tool-Aufrufe.

`true` — Der Inhalt des Ereignisses wird direkt als User-Message an das LLM übergeben:
- Bei `analysis_result`: der vollständige Analysetext des AA-Agenten
- Bei `timer`: eine generische Nachricht ("Periodic analysis cycle...")
- Bei anderen Ereignissen: Trigger-Name, Quelle und Payload-Details

**Beispiel — AA → BA Kette:**

Ein AA-Agent analysiert EURUSD und veröffentlicht ein `analysis_result` mit dem Inhalt: *"BUY, confidence 0.87, entry 1.0920, SL 1.0880"*. Ein BA-Agent ist so konfiguriert, dass `analysis_result` ihn auslöst.

- `pass_trigger=false`: Der BA wird zwar geweckt, aber das LLM bekommt eine leere Nachricht — es weiß nicht, was der AA analysiert hat. Nur sinnvoll wenn der BA das Ergebnis stattdessen selbst per Tool abruft.
- `pass_trigger=true`: Der BA bekommt den Analysetext direkt als User-Message und kann sofort darauf reagieren, z. B. eine Order aufgeben.

**Faustregel:**
- AA-Agent mit `m5_agent_trigger` → `false` (holt Marktdaten selbst per Tools)
- BA-Agent mit `analysis_result`-Trigger → `true` (muss wissen was analysiert wurde)
- Timer-Agenten → meist `false` (der Timer-Text enthält keine nützlichen Daten)

---

### Comment

Freitextfeld für interne Notizen, z. B. `"Analyse-Agent für Europa-Session"`. Hat keinen Einfluss auf das Laufzeitverhalten. Dient der Lesbarkeit der Config-Datei.

---

### Pair

Das Handelspaar, für das dieser Agent zuständig ist, z. B. `EURUSD`, `GBPUSD`, `USDJPY`.  
**Format:** 6 Zeichen, Großbuchstaben. Wird automatisch in Großbuchstaben umgewandelt.

- Nur aktiv wenn **Type = AA**
- Bei anderen Typen (BA, GA, AD) ist das Feld deaktiviert
- Pflichtfeld für AA-Agenten

Spezialwert `ALL___` kann verwendet werden, wenn der Agent für alle Paare gelten soll (sofern vom Backend unterstützt).

---

### Type

Der Rollen-Code des Agenten:

| Code | Bezeichnung | Verwendung |
|---|---|---|
| **AA** | Analysis Agent | Analysiert Marktdaten, trifft Handelsentscheidungen, ist paar-spezifisch |
| **BA** | Broker Agent | Kommuniziert mit dem Broker-Adapter, führt Orders aus |
| **GA** | Global Agent | Systemweite Aufgaben, z. B. Risikomanagement |
| **AD** | Adapter | Systeminterne Verwendung (z. B. Bridge-Agents) |

Der Type beeinflusst, welche Felder aktiv sind (z. B. *Pair* nur bei AA) und wie das Routing intern funktioniert.

---

### LLM

Das LLM-Modul, das dieser Agent verwenden soll. Die Auswahlmöglichkeiten kommen aus dem Abschnitt `modules.llm` der `system.json5`.

Jedes LLM-Modul hat seinen eigenen Modell-Provider, Kontext-Limit und ggf. eigene Default-Einstellungen. Pflichtfeld — ohne LLM-Auswahl kann der Agent nicht gespeichert werden.

---

### Broker

Das Broker-Modul, dem dieser Agent zugeordnet ist. Die Auswahlmöglichkeiten kommen aus dem Abschnitt `modules.broker` der `system.json5`.

Bestimmt, über welchen Broker-Adapter der Agent Kontodaten, Kurse und Order-Ausführung erhält. Pflichtfeld.

---

### Temperature

Steuert die Zufälligkeit der LLM-Ausgaben:

| Wert | Bedeutung |
|---|---|
| `-- module default --` (leer) | Der im LLM-Modul hinterlegte Standardwert wird verwendet |
| `0.1` | Sehr deterministisch — geeignet für Analyse- und Ausführungs-Agenten |
| `0.5` | Ausgeglichen |
| `1.0` | Kreativ und variabel |

Für Analyse- und Handelsagenten wird `0.1` empfohlen. Höhere Werte nur für Agenten sinnvoll, die kreative oder variierende Ausgaben produzieren sollen (z. B. Reporting-Agenten).

---

### Snapshot Profile

Optionales benanntes Profil aus dem Snapshot-Config-Bereich. Wenn gesetzt, baut das System zur Laufzeit automatisch einen Markt-Kontext-Block (Kurse, Indikatoren, Orderbook-Status etc.) und fügt ihn in den Agenten-Prompt ein.

**Ohne Profil:** Der Agent muss alle Kontextinformationen selbst über Tools abrufen.  
**Mit Profil:** Der Kontext ist bereits im Prompt — der Agent spart Tool-Aufrufe und erhält strukturierte Daten direkt.

Leer lassen, wenn kein Snapshot benötigt wird oder der Agent seinen eigenen Kontext über Tools aufbaut.

---

### Decision Prompt Profile

Optionales benanntes Prompt-Profil. Überschreibt oder erweitert das Standard-Entscheidungsverhalten des Agenten für diesen spezifischen Anwendungsfall.

Kann verwendet werden, um denselben Basisagenten mit unterschiedlichen Entscheidungslogiken zu betreiben, ohne den System Prompt zu ändern.

---

### Timer Interval

Zeitintervall in Sekunden, in dem der Agent periodisch ausgelöst wird — **nur aktiv wenn `timer` als Kickoff Trigger eingetragen ist**.

Standardwert: `300` (5 Minuten). Das Feld ist deaktiviert und ausgegraut solange kein `timer`-Trigger aktiv ist.

Beispiele:
- `60` — jede Minute
- `300` — alle 5 Minuten
- `3600` — stündlich

---

### AnyCandle

Bestimmt, auf jede wievielte M5-Kerze (`m5_agent_trigger`) der Agent reagiert.

| Wert | Effekt |
|---|---|
| `1` | Agent läuft auf jede 5-Minuten-Kerze |
| `3` | Agent läuft auf jede dritte Kerze (entspricht 15 Minuten) |
| `12` | Agent läuft einmal pro Stunde |

Nur relevant wenn `m5_agent_trigger` als Kickoff Trigger aktiv ist. Mindestwert: `1`.

---

### System Prompt

Der primäre Instruktionstext für den LLM-Agenten. Definiert, wie sich der Agent verhält, welche Entscheidungslogik er verwendet, was er tun soll und was nicht.

Pflichtfeld — ohne System Prompt wird die Konfiguration nicht gespeichert.

- Schaltfläche **Copy** (oben rechts): kopiert den aktuellen Prompt in die Zwischenablage
- Schaltfläche **Expand** (Quadrat-Icon): öffnet den Prompt in einem Vollbild-Editor-Fenster für komfortables Bearbeiten langer Prompts

Der Prompt hat direkten Einfluss auf die Qualität der Analyse und die Entscheidungslogik. Änderungen am System Prompt sollten sorgfältig getestet werden.

---

### Kickoff Triggers

Ereignisse, die den Agenten auslösen. Der Agent ist inaktiv, bis eines der konfigurierten Ereignisse eintrifft.

**Verfügbare Trigger:**

| Trigger | Bedeutung |
|---|---|
| `m5_agent_trigger` | Jede neue 5-Minuten-Kerze (Standardwert) |
| `prompt_updated` | Der System Prompt des Agenten wurde geändert |
| `agent_query` | Ein anderer Agent oder Prozess fragt diesen Agenten direkt an |
| `analysis_result` | Ein Analyse-Ergebnis wurde im Bus veröffentlicht |
| `signal_generated` | Ein Handelssignal wurde erzeugt |
| `account_status_updated` | Der Kontostatus (Balance, Margin etc.) hat sich geändert |
| `risk_breach` | Ein Risikolimit wurde überschritten |
| `order_book_sync_discrepancy` | Inkonsistenz im Orderbook erkannt |
| `timer` | Periodische Ausführung gemäß *Timer Interval* |

**Bedienung:**
1. Gewünschten Trigger aus dem Dropdown wählen
2. Grünen `+`-Button klicken, um ihn hinzuzufügen
3. Zum Entfernen auf das rote `−` neben dem Trigger-Tag klicken

Mehrere Trigger gleichzeitig sind möglich. Mindestens ein Trigger ist erforderlich.

---

### Session Filter

Schränkt ein, zu welchen Handelszeiten der Agent aktiv ist. Wenn kein Filter eingetragen ist, reagiert der Agent unabhängig von der Tageszeit.

**Verfügbare Sessions:**

| Session | Typische Handelszeit (UTC) |
|---|---|
| `sydney` | 21:00 – 06:00 |
| `tokyo` | 00:00 – 09:00 |
| `london` | 07:00 – 16:00 |
| `new_york` | 12:00 – 21:00 |

**Pre / Post Offsets (in Minuten):**

- **Pre** — verschiebt den Session-Beginn. Negativer Wert = Agent startet früher (z. B. `-15` = 15 Minuten vor Session-Open)
- **Post** — verschiebt das Session-Ende. Positiver Wert = Agent bleibt länger aktiv (z. B. `30` = 30 Minuten nach Session-Close)

**Bedienung:**
1. `Add session` klicken
2. Session aus dem Dropdown wählen
3. Pre/Post-Offsets nach Bedarf anpassen
4. Mehrere Sessions möglich — der Agent ist aktiv wenn *mindestens eine* Session aktiv ist

---

### Allowed Tools

Die Werkzeuge (Tools), die der LLM-Agent in dieser Konfiguration aufrufen darf. Der Agent kann ausschließlich Tools aus dieser Liste verwenden — alle anderen sind blockiert.

**Bedienung:**
1. Tool aus dem Dropdown wählen (Liste kommt aus der Backend-Konfiguration)
2. Grünen `+`-Button klicken, um es hinzuzufügen
3. Zum Entfernen auf das rote `−` neben dem Tool-Tag klicken

**Standard-Tools:** `get_candles`, `calculate_indicator`, `raise_alarm`

Welche Tools sinnvoll sind, hängt vom Agenten-Typ ab. AA-Agenten brauchen Marktdaten-Tools; BA-Agenten brauchen Order-Ausführungs-Tools.

---

### Tool Config — Forced Arguments

Für jedes erlaubte Tool können hier Argumente fix vorgegeben werden. Diese Werte werden zur Laufzeit automatisch eingesetzt und **können vom LLM nicht überschrieben werden**.

Sinnvoll, um sicherzustellen dass der Agent immer das richtige Paar, den richtigen Broker oder korrekte Kontextparameter verwendet — unabhängig davon, was das Modell zu senden versucht.

**Platzhalter** können als Argumente verwendet werden:

| Platzhalter | Wird ersetzt durch |
|---|---|
| `{llm}` | Name des konfigurierten LLM-Moduls |
| `{broker}` | Name des konfigurierten Broker-Moduls |
| `{pair}` | Das konfigurierte Handelspaar |
| `{type}` | Der Agenten-Typ (AA, BA, ...) |
| `{name}` | Der Namensteil der Agent-ID |
| `{agent_id}` | Die vollständige Agent-ID |

**Bedienung:** Für jedes erlaubte Tool wird ein Eingabeblock angezeigt. Felder die leer bleiben, werden nicht erzwungen — der LLM kann sie dann frei belegen. Mit dem **Clear**-Button werden alle Forced Arguments eines Tools auf einmal gelöscht.

> Pflichtargumente des Tools sind mit `*` markiert.

---

### Max Tool Turns

Maximale Anzahl an Tool-Aufrufen, die der Agent in einem einzigen Ausführungszyklus durchführen darf.

Verhindert Endlosschleifen, falls das Modell in einen rekursiven oder hängenden Tool-Aufruf-Muster gerät.

Standardwert: `8`. Mindestwert: `1`.

Für komplexe Analyse-Agenten mit vielen Tool-Calls kann ein höherer Wert sinnvoll sein. Für einfache Agenten reicht `3–5`.

---

### Max Tokens

Maximales Token-Budget für eine einzelne Antwort bzw. einen Ausführungszyklus des Agenten.

Standardwert: `4096`. Mindestwert: `1`.

Beeinflusst sowohl die Kosten als auch die mögliche Ausgabelänge. Für ausführliche Analysen oder lange System Prompts entsprechend erhöhen. Das tatsächliche Limit des Modells (vom LLM-Modul) kann diesen Wert zusätzlich begrenzen.

---

## Sidebar: Live Summary und Validierung

### Live Summary

Zeigt die aktuelle Konfiguration als Text-Vorschau — so wie sie in der `system.json5` gespeichert werden würde. Hilfreich zur schnellen Kontrolle vor dem Speichern.

### Validierung

Listet alle Fehler auf, die das Speichern verhindern würden:

- Agent-ID-Format ungültig
- Pflichtfelder fehlen (LLM, Broker, Type, System Prompt)
- Kein Kickoff Trigger eingetragen

Sind keine Fehler vorhanden, erscheint `No validation issues detected.` in Grün.

---

## Typischer Workflow: Neuen Agenten anlegen

1. **New Empty Agent** klicken — alle Felder werden geleert
2. **Agent ID** im korrekten Format eingeben
3. **Type** wählen (meistens `AA`)
4. **LLM** und **Broker** aus den Dropdowns auswählen
5. **Pair** eintragen (bei AA-Agenten)
6. **System Prompt** verfassen oder einfügen — ggf. Expand-Button für den Vollbild-Editor nutzen
7. **Kickoff Triggers** konfigurieren
8. **Allowed Tools** hinzufügen
9. Bei Bedarf: Session Filter, Forced Arguments, Timer einstellen
10. Rechte Sidebar prüfen — keine Validierungsfehler
11. **Save As New** klicken

---

## Speicherverhalten und Hot Reload

Beim Klick auf **Update** oder **Save As New** führt die UI folgende Schritte aus:
1. Vollständige Konfigurationsvalidierung
2. Aktualisierter Agent-Eintrag wird in `config/system.json5` geschrieben
3. Ein `agent_config_requested`-Ereignis wird auf dem Event-Bus gesendet

Das `agent_config_requested`-Ereignis löst einen Hot Reload der Agenten-Konfigurationen aus — der Agent wird mit den neuen Einstellungen **ohne vollständigen Systemneustart** neu geladen.

**Was einen Neustart erfordert:**
- Wechsel des Broker-Moduls (Broker-Adapter werden beim Start initialisiert)
- Wechsel des LLM-Moduls (LLM-Clients werden beim Start initialisiert)
- Erstmaliges Hinzufügen eines Agenten mit `enable=true`

**Was sicher hot-geladen wird:**
- System Prompt
- Erlaubte Tools und Forced Arguments
- Session Filter
- AnyCandle-Divisor
- Timer-Intervall
- Max Tool Turns / Max Tokens
- enable-Flag (Deaktivierung lädt hot; Reaktivierung erfordert Neustart)

---

## Agent-ID-Format — Vollständige Spezifikation

Die Agent-ID ist der primäre Bezeichner für jeden Agenten im System. Sie wird für Routing, Logging und Event-Targeting verwendet.

**Format:** `BROKER(5)-PAIR(6)-TYP(2)-NAME(1-5)`

Jedes Segment ist durch einen Bindestrich getrennt. Keine anderen Zeichen erlaubt.

### BROKER (5 Zeichen)

Ein 5-Zeichen-Code der identifiziert zu welchem Broker oder Broker-Gruppe dieser Agent gehört. Muss exakt 5 Zeichen sein — mit Unterstrichen auffüllen wenn nötig.

Beispiele:
- `OXS_T` — OXS-Broker, Test-/Demo-Konto
- `OXS_L` — OXS-Broker, Live-Konto
- `SYSTM` — Systemebenen-Agenten nicht an einen Broker gebunden
- `GLOBL` — Globale Agenten

Dieses Segment wird für Event-Routing verwendet — ein `analysis_result` von einem EURUSD-Agenten kann auf den BA-Agenten mit dem passenden Broker-Code geroutet werden.

### PAIR (6 Zeichen)

Das Währungspaar für das dieser Agent arbeitet, exakt 6 Zeichen. Mit Unterstrichen auffüllen wenn nötig.

Beispiele:
- `EURUSD` — Euro vs. US-Dollar
- `GBPUSD` — Britisches Pfund vs. US-Dollar
- `USDJPY` — US-Dollar vs. Japanischer Yen
- `ALL___` — Gilt für alle Paare (für BA- und GA-Agenten die mehrere Paare bedienen)

AA-Agenten müssen immer ein spezifisches Pair haben (kein `ALL___`). BA- und GA-Agenten verwenden typischerweise `ALL___`.

### TYP (2 Zeichen)

Exakt 2 Zeichen zur Identifikation der Agenten-Rolle:
- `AA` — Analysis Agent (analysiert Marktdaten, produziert Handelsentscheidungen)
- `BA` — Broker/Execution Agent (kommuniziert mit Broker, platziert Orders)
- `GA` — Global/System Agent (systemweite Aufgaben: Risiko, Reporting, Monitoring)
- `AD` — Adapter (interne Bridge-Agenten)

### NAME (1-5 Zeichen)

Kurze beschreibende Bezeichnung für den Agenten. 1 bis 5 Zeichen.

Gängige Namenskonventionen:
- `ANLYS` — Analyse-Agent
- `EXEC` — Ausführungs-Agent
- `RELAY` — Relay-/Routing-Agent
- `REPO` — Reporting-Agent
- `RISK` — Risikomanagement-Agent
- `MON` — Monitoring-Agent

**Vollständige Beispiele:**
- `OXS_T-EURUSD-AA-ANLYS` — OXS Test-Broker, EURUSD-Analyse-Agent namens ANLYS
- `OXS_T-ALL___-BA-ANLYS` — OXS Test-Broker, Alle-Paare-Ausführungs-Agent
- `SYSTM-ALL___-GA-REPO` — Systemebenen-Globaler-Reporting-Agent

---

## Typ — Detaillierte Aufschlüsselung

### AA — Analysis Agent

Das primäre Arbeitstier. AA-Agenten sind paar-spezifisch und zuständig für:
- Marktdaten sammeln (Kerzen, Indikatoren, Swing-Level)
- Marktbedingungen gegen die System-Prompt-Anweisungen analysieren
- Eine strukturierte Entscheidung produzieren (BUY/SELL/NEUTRAL, Konfidenz, Entry, SL, TP)
- `analysis_result`-Ereignisse veröffentlichen die von BA-Agenten oder ECs verarbeitet werden

**Typische Konfiguration für AA-Agenten:**
- `event_triggers`: `[m5_agent_trigger]`
- `pass_trigger`: `false` (baut eigenen Kontext über Tools oder Snapshot-Profil)
- `snapshot_profile`: auf ein AA-spezifisches Profil gesetzt
- `AnyCandle`: 3 oder 6 für weniger häufige Analysen (alle 15 oder 30 Minuten)
- `session_filter`: auf London und/oder New York beschränkt

### BA — Broker/Execution Agent

Empfängt Analyseergebnisse und entscheidet ob und wie Trades ausgeführt werden. BA-Agenten:
- Werden durch `ec_output` (vom Event Composer Relay) oder direkt durch `analysis_result` getriggert
- Lesen die via `pass_trigger=true` übergebene Analyse-Payload
- Prüfen Kontostand, bestehende Positionen, Risikolevel
- Rufen `place_order`, `auto_place_order` auf oder tun nichts
- Ein BA-Agent bedient typischerweise alle Paare für einen gegebenen Broker

**Typische Konfiguration für BA-Agenten:**
- `event_triggers`: `[ec_output]`
- `pass_trigger`: `true` (benötigt Analyse-JSON als Eingabe)
- `pair`: `ALL___`
- `snapshot_profile`: keins oder leichtes Konto-Status-Profil
- Erlaubte Tools: `get_open_positions`, `get_account_status`, `place_order`, `auto_place_order`, `close_position`, `modify_order`, `get_order_book`, `raise_alarm`

### GA — Global Agent

Systemweite Agenten die über alle Paare und Broker hinweg operieren. Beispiele:
- Tägliches P&L-Reporting
- Risikolimit-Überwachung
- Systemgesundheitsprüfungen
- Tagesabschluss-Positions-Abstimmung

---

## Session Filter — Umfassender Leitfaden

Der Session Filter schränkt ein wann ein Agent Trigger verarbeitet. Ein Agent mit Session Filter läuft nur wenn mindestens eine seiner konfigurierten Sessions zum Zeitpunkt des Triggers aktiv ist.

**Wichtig:** Session-Zeiten werden gegen den **Kerzen-Zeitstempel** verglichen, nicht gegen die Systemuhr des Servers. Der Wert `broker_candle_utc_offset_hours` in `system.json5` definiert den UTC-Offset der Kerzen-Zeitstempel vom Broker-Datenfeed.

### Session-Fenster (Standard UTC-Zeiten)

| Session | Öffnung UTC | Schließung UTC |
|---|---|---|
| Sydney | 21:00 (Vortag) | 06:00 |
| Tokyo | 00:00 | 09:00 |
| London | 07:00 | 16:00 |
| New York | 12:00 | 21:00 |

Diese sind ungefähre Standard-Zeiten. Die tatsächlichen Öffnungs-/Schließungszeiten passen sich der Sommerzeit (DST) in den jeweiligen Ländern an.

### Pre- und Post-Offsets

| Feld | Bedeutung | Beispiel |
|---|---|---|
| pre (positiv) | Session-Fenster SPÄTER als der offizielle Öffnungszeitpunkt starten | `pre=10` → 10 Minuten nach Session-Öffnung starten |
| pre (negativ) | Session-Fenster FRÜHER als der offizielle Öffnungszeitpunkt starten | `pre=-15` → 15 Minuten vor Session-Öffnung starten |
| post (positiv) | Session-Fenster SPÄTER als der offizielle Schließungszeitpunkt enden | `post=30` → 30 Minuten nach Session-Schließung enden |
| post (negativ) | Session-Fenster FRÜHER als der offizielle Schließungszeitpunkt enden | `post=-30` → 30 Minuten vor Session-Schließung enden |

### Praktisches Berechnungsbeispiel

Agent konfiguriert mit:
- London: `pre=10`, `post=0`
- New York: `pre=0`, `post=-30`
- `broker_candle_utc_offset_hours=3` (Broker-Kerzen sind UTC+3)

**London-Session (Normalzeit BST = UTC+1):**
- Standard London-Öffnung: 07:00 UTC = 10:00 Broker-Zeit
- Mit pre=10: Agent startet um 10:10 Broker-Zeit
- Standard London-Schließung: 16:00 UTC = 19:00 Broker-Zeit
- Mit post=0: Agent endet um 19:00 Broker-Zeit

**New York-Session (Sommerzeit EDT = UTC-4):**
- Standard NY-Öffnung: 12:00 UTC = 15:00 Broker-Zeit
- Mit pre=0: Agent startet um 15:00 Broker-Zeit
- Standard NY-Schließung: 21:00 UTC = 00:00 Broker-Zeit (nächster Tag)
- Mit post=-30: Agent endet um 23:30 Broker-Zeit

**Ergebnis:** Agent läuft von 10:10 bis 19:00 Broker-Zeit (London-Fenster) und von 15:00 bis 23:30 Broker-Zeit (NY-Fenster). Beim London-NY-Überlapp (15:00–19:00 Broker-Zeit) sind beide Sessions aktiv, Agent läuft in beiden Fällen.

### Mehrere Sessions

Wenn mehrere Sessions konfiguriert sind, ist der Agent aktiv wenn **eine** der konfigurierten Sessions aktuell aktiv ist.

### Wann Session Filter verwenden

- **AA-Agenten:** Fast immer Session Filter verwenden — auf Sessions beschränken wo das Pair am liquidesten ist. EURUSD profitiert von London + New York; USDJPY von Tokyo + London-Überlapp.
- **BA-Agenten:** Oft gleicher Filter wie die gepaarten AA-Agenten oder leicht weiteres Fenster.
- **GA-Agenten mit Timern:** Meist kein Filter.

---

## AnyCandle — Frequenzkontrolle

Der `AnyCandle`-Parameter ist ein Divisor der auf das `m5_agent_trigger`-Ereignis angewendet wird. Er steuert wie oft der Agent tatsächlich einen M5-Kerzen-Trigger verarbeitet.

Das System zählt M5-Kerzen und weckt den Agenten nur wenn die Anzahl durch den AnyCandle-Wert teilbar ist.

| AnyCandle | Trigger-Frequenz | Entsprechendes Intervall |
|---|---|---|
| 1 | Jede M5-Kerze | 5 Minuten |
| 2 | Jede 2. Kerze | 10 Minuten |
| 3 | Jede 3. Kerze | 15 Minuten |
| 4 | Jede 4. Kerze | 20 Minuten |
| 6 | Jede 6. Kerze | 30 Minuten |
| 12 | Jede 12. Kerze | 60 Minuten |
| 24 | Jede 24. Kerze | 2 Stunden |
| 48 | Jede 48. Kerze | 4 Stunden |

**Wichtiger Hinweis:** AnyCandle gilt nur für `m5_agent_trigger`. Andere Trigger (z.B. `timer`, `agent_query`) feuern in ihrem eigenen Rhythmus unabhängig von AnyCandle.

**Den richtigen Wert wählen:**
- Für H4- oder D1-Chart-Analysen: AnyCandle=12 (stündlich) oder AnyCandle=48 (4-stündlich) ist sinnvoll
- Für M15-Scalping: AnyCandle=3 (alle 15 Minuten) ist angemessen
- Für aggressive Systeme die alle 5 Minuten überwachen: AnyCandle=1

---

## Tool Config — forced_arguments im Detail

Die `forced_arguments`-Konfiguration in `tool_config` ist ein kritischer Sicherheits- und Konsistenz-Mechanismus. Sie stellt sicher dass bestimmte Tool-Argumente immer auf spezifische Werte gesetzt werden, unabhängig davon was das LLM zu übergeben versucht.

### Warum forced_arguments wichtig ist

Wenn ein BA-Agent `place_order` aufruft, soll garantiert werden dass:
- Das `pair`-Argument mit dem Pair aus dem Analyse-Signal übereinstimmt
- Das `broker`-Argument mit dem konfigurierten Broker übereinstimmt
- `comment` immer die agent_id enthält für Nachvollziehbarkeit

Ohne forced_arguments könnte das LLM einen falschen Pair-Namen halluzinieren oder den Broker-Kontext vergessen.

### Format

```json
{
  "tool_name": {
    "argument_name": "wert_oder_platzhalter"
  }
}
```

### Platzhalter

Platzhalter werden zur Laufzeit aus der eigenen Konfiguration des Agenten aufgelöst:

| Platzhalter | Löst auf zu |
|---|---|
| `{pair}` | Das konfigurierte Pair des Agenten (z.B. `EURUSD`) |
| `{broker}` | Der Name des konfigurierten Broker-Moduls |
| `{llm}` | Der Name des konfigurierten LLM-Moduls |
| `{agent_id}` | Die vollständige Agent-ID (z.B. `OXS_T-EURUSD-AA-ANLYS`) |
| `{type}` | Der Agenten-Typ-Code (`AA`, `BA`, `GA`) |
| `{name}` | Das Namenssegment der Agent-ID (z.B. `ANLYS`) |

### Beispiel-Konfiguration

Für einen BA-Agenten der immer auf dem richtigen Pair mit dem richtigen Broker handeln soll:

```json
{
  "place_order": {
    "broker": "{broker}",
    "comment": "{agent_id}"
  },
  "get_candles": {
    "pair": "{pair}",
    "timeframe": "H1"
  },
  "get_swing_levels": {
    "pair": "{pair}",
    "timeframe": "H4"
  }
}
```

### Wechselwirkung mit LLM

Wenn das LLM `get_candles` mit `{"pair": "GBPUSD", "timeframe": "M5"}` aufruft, aber forced_arguments `{"pair": "{pair}", "timeframe": "H1"}` für einen EURUSD-Agenten hat, läuft das Tool tatsächlich mit `pair=EURUSD, timeframe=H1`. Die Werte des LLMs werden still überschrieben.

---

## Vollständige Agenten-Konfigurationsworkflow-Beispiele

### Beispiel: EURUSD AA-Agent einrichten

**Konfigurationswerte:**
- Agent ID: `OXS_T-EURUSD-AA-ANLYS`
- Type: `AA`
- Enable: `true`
- LLM: `azure_azmin`
- Broker: `oxs_test`
- Pair: `EURUSD`
- AnyCandle: `3` (alle 15 Minuten)
- pass_trigger: `false`
- snapshot_profile: `aa_eurusd_v1`
- event_triggers: `[m5_agent_trigger]`
- session_filter: London (pre=10, post=0), New York (pre=0, post=-30)
- Erlaubte Tools: `get_candles`, `calculate_indicator`, `get_swing_levels`, `get_session_status`, `raise_alarm`
- forced_arguments: `get_candles: {pair: {pair}}`, `calculate_indicator: {pair: {pair}}`, `get_swing_levels: {pair: {pair}}`
- Max Tool Turns: `10`
- Max Tokens: `8000`

### Beispiel: BA-Ausführungs-Agent einrichten

**Konfigurationswerte:**
- Agent ID: `OXS_T-ALL___-BA-ANLYS`
- Type: `BA`
- Enable: `true`
- LLM: `azure_azmin`
- Broker: `oxs_test`
- Pair: `ALL___`
- pass_trigger: `true`
- event_triggers: `[ec_output]`
- Erlaubte Tools: `get_open_positions`, `get_account_status`, `place_order`, `auto_place_order`, `close_position`, `modify_order`, `get_order_book`, `raise_alarm`
- forced_arguments: `place_order: {broker: {broker}, comment: {agent_id}}`, `auto_place_order: {broker: {broker}}`
- Max Tool Turns: `6`
- Max Tokens: `4000`

### Beispiel: GA-Reporting-Agent einrichten

**Konfigurationswerte:**
- Agent ID: `SYSTM-ALL___-GA-REPO`
- Type: `GA`
- Enable: `true`
- LLM: `azure_azmin`
- Broker: `oxs_test`
- Pair: `ALL___`
- pass_trigger: `false`
- event_triggers: `[timer]`
- Timer: aktiviert, interval_seconds: `3600`
- session_filter: (keins — läuft jederzeit)
- Erlaubte Tools: `get_account_status`, `get_open_positions`, `get_order_book`, `get_last_decision`, `raise_alarm`
- Max Tool Turns: `5`
- Max Tokens: `2000`

---

## Häufige Fehler und wie man sie vermeidet

### Falsches Agent-ID-Format

**Fehler:** `EURUSD-AA-ANLYS` (fehlendes BROKER-Segment, falsche Längen)

**Korrekt:** `OXS_T-EURUSD-AA-ANLYS` (alle 4 Segmente, korrekte Längen)

Das Validierungs-Panel hebt Format-Fehler hervor bevor gespeichert werden kann.

### BA-Agent mit pass_trigger=false

**Fehler:** BA-Agent mit `pass_trigger=false` und `ec_output`-Trigger. Der Agent wacht auf aber das LLM erhält eine leere Nachricht — es weiß nicht was gehandelt werden soll.

**Korrekt:** BA-Agenten sollten bei Analyse-Ereignissen fast immer `pass_trigger=true` haben.

### Fehlender Session Filter bei AA-Agent

**Fehler:** AA-Agent läuft rund um die Uhr auf jede M5-Kerze und verschwendet API-Aufrufe während liquiditätsschwacher Zeiten.

**Korrekt:** Session Filter hinzufügen der den AA-Agenten auf London und/oder New York beschränkt.

### AnyCandle=1 für einen Tageschart-Analyse-Agenten

**Fehler:** Ein Agent der D1-Charts analysiert läuft alle 5 Minuten und ruft dieselben D1-Kerzen ab die sich bis zum nächsten Tag nicht ändern.

**Korrekt:** AnyCandle=48 (alle 4 Stunden) oder AnyCandle=12 (stündlich) für Agenten die höhere Zeitrahmen analysieren.

### Widersprüchliche forced_arguments

**Fehler:** `get_candles.timeframe="H1"` in forced_arguments setzen, aber System Prompt weist LLM an "M15-Kerzen zu analysieren" — das LLM versucht `get_candles` mit `timeframe="M15"` aufzurufen, erhält aber immer H1-Daten.

**Korrekt:** Forced Arguments und System-Prompt-Anweisungen konsistent halten.
