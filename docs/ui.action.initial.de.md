[Zurück zu Action](ui.action.de.md)

# Initial — Systemübersicht und Steuerung

Die **Initial**-Seite ist die Startseite der Action-Ansicht. Sie zeigt auf einen Blick den Gesamtzustand des Systems: welche Version läuft, ob alle LLM- und Broker-Verbindungen aktiv sind, und in welchem Zustand sich jeder konfigurierte Agent befindet. Von hier aus lässt sich das System pausieren, fortsetzen oder neu starten.

---

## 1. Versionsbereich

Der Versionsbereich befindet sich oben links auf der Initial-Seite. Er zeigt zwei Versionsnummern und stellt die wichtigsten Systemsteuerungs-Buttons bereit.

### 1.1 Lokale Version

Die **lokale Version** (z. B. `v0.7.4`) ist die aktuell installierte und laufende Version von OpenForexAI. Diese Versionsnummer stammt direkt aus dem lokalen Paket und ändert sich erst nach einem expliziten Update.

### 1.2 Internet-Version

Die **Internet-Version** (z. B. `v0.7.5`) ist die neueste verfügbare Version auf GitHub. Das System prüft beim Laden der Seite, ob eine neue Version vorhanden ist. Wenn die Internet-Version höher ist als die lokale Version, erscheint ein visueller Hinweis (Badge oder Hervorhebung), der auf ein verfügbares Update aufmerksam macht.

Ist keine Internetverbindung vorhanden oder schlägt die Abfrage fehl, wird statt der Versionsnummer ein Fehler- oder Ladeindikator angezeigt.

### 1.3 Update-Button

Der **Update**-Button lädt die neueste Version von GitHub herunter und installiert sie lokal. Der Ablauf:

1. Das System prüft, ob eine neuere Version als die aktuell installierte auf GitHub verfügbar ist.
2. Falls ja, wird das neue Paket heruntergeladen.
3. Die Dateien werden lokal aktualisiert.
4. Ein anschließender Neustart über **Restart Now** ist erforderlich, damit die neue Version aktiv wird.

**Wichtiger Hinweis:** Führen Sie ein Update nie durch, während aktive Trades offen sind, es sei denn, Sie haben die Konsequenzen geprüft. Pausieren Sie das System zuerst mit **Suspend**, vergewissern Sie sich über alle offenen Positionen, und führen Sie erst dann das Update durch.

### 1.4 Suspend-Button

Der **Suspend**-Button pausiert alle Agent-Zyklen sofort. Das bedeutet:

- Kein Agent wird durch neue M5-Kerzen ausgelöst.
- Laufende Zyklen, die bereits gestartet wurden, werden zu Ende geführt — kein harter Abbruch mitten in der Analyse.
- Neue Trigger werden ignoriert oder in eine Warteschlange gestellt, je nach Konfiguration.
- LLM-Verbindungen und Broker-Verbindungen bleiben aktiv — es werden nur keine neuen Analysen gestartet.

Der Suspend-Zustand wird durch ein visuelles Badge auf der Initial-Seite angezeigt (z. B. orangefarbenes Badge „SUSPENDED" neben dem Systemstatus).

**Wann Suspend verwenden:**
- Vor Konfigurationsänderungen, die laufende Agents beeinflussen könnten.
- Vor einem Update.
- Wenn Sie manuell in den Markt eingreifen möchten, ohne dass die Agents gleichzeitig Signale erzeugen.
- Während der Fehlerbehebung, um den Ereignisstrom zu „einzufrieren" und ohne neue Ereignisse analysieren zu können.
- Bei unerwarteten Marktbedingungen (z. B. starke Nachrichtenereignisse), wenn Sie die Kontrolle vorübergehend manuell übernehmen möchten.

### 1.5 Continue-Button

Der **Continue**-Button hebt den Suspend-Zustand auf und setzt alle Agent-Zyklen fort. Nach dem Klick:

- Agents reagieren wieder auf neue M5-Kerzen-Trigger.
- Falls Trigger während der Pause aufgelaufen sind, werden diese je nach Konfiguration verarbeitet oder übersprungen.
- Der Status-Badge wechselt zurück zu „RUNNING" oder dem normalen Betriebszustand.

Continue ist nur aktiv, wenn das System zuvor durch Suspend pausiert wurde.

### 1.6 Restart Now

Der **Restart Now**-Button startet die Runtime von OpenForexAI sofort neu, ohne den gesamten Server-Prozess neu zu starten. Dies ist nützlich nach:

- Konfigurationsänderungen, die einen Neustart erfordern (z. B. neue Agents hinzugefügt, LLM-Module geändert).
- Updates, die mit dem Update-Button installiert wurden.
- Unerwarteten Fehlerzuständen, aus denen sich das System nicht selbst erholen kann.

**Ablauf eines Restart Now:**

1. Alle laufenden Agent-Zyklen werden so schnell wie möglich abgeschlossen oder sicher unterbrochen.
2. Alle Verbindungen (Broker, LLM) werden sauber geschlossen.
3. Die Runtime wird neu initialisiert: Konfiguration wird neu geladen, Module werden neu gestartet.
4. Broker- und LLM-Verbindungen werden neu aufgebaut.
5. Agents werden in ihren Ausgangszustand zurückversetzt und warten auf den nächsten Trigger.

Der Prozess dauert je nach Systemlast und Netzwerkverbindung zwischen 5 und 30 Sekunden. Während des Neustarts ist die UI zugänglich, zeigt aber einen Ladezustand an.

---

## 2. LLM-Schnittstellen

Der Abschnitt **LLM-Schnittstellen** zeigt alle konfigurierten LLM-Module (Large Language Model-Dienste) und ihren aktuellen Verbindungsstatus.

### 2.1 Was ist ein LLM-Modul?

Ein LLM-Modul ist eine konfigurierte Verbindung zu einem KI-Sprachmodell-Dienst. OpenForexAI unterstützt verschiedene Anbieter, z. B.:
- **Azure OpenAI** (typisch: `azure_azmin`)
- **OpenAI direkt**
- **Anthropic Claude**
- **Lokale Modelle** (z. B. über Ollama)

Jedes Modul hat eine eindeutige Modul-ID (z. B. `llm:azure_azmin`), die in der Agents-Konfiguration referenziert wird.

### 2.2 Status-Badge

Jedes LLM-Modul wird mit einem farbigen Status-Badge angezeigt:

| Badge | Bedeutung |
|-------|-----------|
| **VERBUNDEN** (grün) | Das Modul ist erreichbar und betriebsbereit. |
| **GETRENNT** (rot) | Das Modul ist nicht erreichbar. Mögliche Ursachen: API-Key ungültig, Netzwerkproblem, Dienst nicht verfügbar. |
| **VERBINDEN…** (gelb/orange) | Das Modul versucht gerade, eine Verbindung herzustellen oder neu zu verbinden. |
| **FEHLER** (rot mit Details) | Ein spezifischer Fehler ist aufgetreten. Hovern über das Badge oder Klicken zeigt Details. |

### 2.3 Was passiert bei einem getrennten LLM-Modul?

Wenn ein LLM-Modul als **GETRENNT** angezeigt wird:
- Agents, die dieses Modul verwenden, können keine neuen Analysen durchführen.
- Im Monitor erscheinen Fehlermeldungen (z. B. `llm_error` im LLM-Events-Tab).
- Agents werden zwar durch M5-Kerzen getriggert, scheitern aber beim LLM-Aufruf-Schritt.

**Maßnahmen bei getrenntem LLM:**
1. Prüfen Sie die Netzwerkverbindung.
2. Überprüfen Sie den API-Key in der Konfigurationsdatei (`system.json5`).
3. Prüfen Sie den Status des LLM-Anbieters (Azure-Portal, OpenAI-Status-Seite, Anthropic-Status).
4. Versuchen Sie einen **Restart Now**, um die Verbindung neu aufzubauen.
5. Falls das Problem anhält: Prüfen Sie die Logs auf detaillierte Fehlermeldungen.

### 2.4 Mehrere LLM-Module

Ein System kann mehrere LLM-Module gleichzeitig konfiguriert haben, z. B. ein Azure-Modul für Produktions-Agents und ein lokales Modell für Test-Agents. Jedes Modul wird separat angezeigt und hat einen eigenen Status-Badge.

---

## 3. Broker-Schnittstellen

Der Abschnitt **Broker-Schnittstellen** zeigt alle konfigurierten Broker-Module und ihren aktuellen Status.

### 3.1 Was ist ein Broker-Modul?

Ein Broker-Modul ist eine konfigurierte Verbindung zu einem Forex-Broker oder einer Trading-Plattform. OpenForexAI unterstützt verschiedene Broker-Adapter, z. B. **OXS** (OANDA-kompatibel):

- `broker.OXS_T` — Test-Account (Paper-Trading)
- `broker.OXS_L` — Live-Account (Echtgeld)

Jedes Broker-Modul hat eine eindeutige Modul-ID und ist mit einem bestimmten Handelskonto verknüpft.

### 3.2 Status-Badge

| Badge | Bedeutung |
|-------|-----------|
| **VERBUNDEN** (grün) | Der Broker ist erreichbar, die API antwortet, und Konto-Daten wurden erfolgreich abgerufen. |
| **GETRENNT** (rot) | Der Broker ist nicht erreichbar. Kein Trading möglich. |
| **SYNCHRONISIERT** (grün mit Zusatz) | Verbunden und Konto-Synchronisation erfolgreich abgeschlossen. Alle offenen Positionen sind bekannt. |
| **SYNC-FEHLER** (orange) | Verbunden, aber die Synchronisation der offenen Positionen ist fehlgeschlagen oder veraltet. |
| **RECONNECTING** (gelb) | Der Broker-Adapter versucht, die Verbindung automatisch wiederherzustellen. |

### 3.3 Broker-Details

Weitere Details zum Broker-Status sind im Monitor unter dem **Broker Events**-Tab einsehbar. Dort sind HTTP-Requests und -Responses, Synchronisations-Ereignisse und Verbindungsstatus-Events sichtbar.

### 3.4 Was passiert bei einem getrennten Broker?

Wenn ein Broker als **GETRENNT** angezeigt wird:
- Agents des Typs BA (Ausführungs-Agent), die diesen Broker verwenden, können keine Trades öffnen oder schließen.
- Bereits offene Positionen beim Broker sind weiterhin aktiv — OpenForexAI hat jedoch keine Kontrolle darüber, bis die Verbindung wiederhergestellt ist. Stop-Loss und Take-Profit, die beim Broker hinterlegt sind, greifen weiterhin.
- AA-Agents können weiterhin Analysen durchführen, benötigen aber den Broker für aktuelle Kerzen-Daten.

**Maßnahmen bei getrenntem Broker:**
1. Prüfen Sie Ihre Internetverbindung.
2. Prüfen Sie, ob der Broker-Dienst/die API-Plattform erreichbar ist.
3. Überprüfen Sie API-Key und Account-ID in der Konfiguration.
4. Warten Sie auf den automatischen Reconnect-Versuch (sichtbar am RECONNECTING-Badge).
5. Falls kein automatischer Reconnect: **Restart Now** klicken.
6. Nach Wiederherstellung: Im Orderbook prüfen, ob alle Positionen korrekt synchronisiert wurden.

### 3.5 Test- vs. Live-Broker

Es ist möglich, sowohl einen Test-Broker (`OXS_T`) als auch einen Live-Broker (`OXS_L`) gleichzeitig konfiguriert zu haben. Beide werden separat angezeigt. Achten Sie darauf, dass Agents mit dem korrekten Broker-Modul verknüpft sind, um unbeabsichtigtes Live-Trading zu vermeiden.

---

## 4. Konfigurierte Agents-Tabelle

Die **Agents-Tabelle** ist das zentrale Element der Initial-Seite. Sie zeigt alle konfigurierten Agents mit ihren wichtigsten Eigenschaften und ihrem aktuellen Status.

### 4.1 Spalten der Tabelle

#### Agent-ID

Die eindeutige Kennung des Agents, z. B. `OXS_T-EURUSD-AA-ANLYS` oder `OXS_T-EURUSD-BA-TRADE`.

Die empfohlene Namenskonvention folgt dem Schema:

```
{Broker}-{Pair}-{Typ}-{Aufgabe}
```

Beispiele:
- `OXS_T-EURUSD-AA-ANLYS` — OANDA Test-Broker, EUR/USD, Analyse-Agent, Aufgabe: Analyse
- `OXS_T-EURUSD-BA-TRADE` — OANDA Test-Broker, EUR/USD, Ausführungs-Agent, Aufgabe: Trading
- `OXS_L-GBPUSD-AA-ANLYS` — OANDA Live-Broker, GBP/USD, Analyse-Agent

#### Status

Der aktuelle Betriebsstatus des Agents:

| Status | Farbe | Bedeutung |
|--------|-------|-----------|
| **IDLE** | grau/blau | Agent wartet auf den nächsten Trigger (M5-Kerze). Normaler Ruhezustand. |
| **RUNNING** | grün | Agent führt gerade einen Analyse- oder Ausführungszyklus durch. |
| **SUSPENDED** | orange | Agent ist durch Suspend deaktiviert und reagiert nicht auf Trigger. |
| **ERROR** | rot | Agent ist in einen Fehlerzustand geraten. Details im Monitor-Tab. |
| **WAITING** | gelb | Agent wartet auf eine externe Ressource (LLM-Antwort, Broker-Antwort). |
| **DISABLED** | grau (dunkel) | Agent ist in der Konfiguration deaktiviert und führt keine Zyklen aus. |

#### Typ

Der Agent-Typ bestimmt die grundlegende Funktionsweise:

| Typ | Vollname | Beschreibung |
|-----|----------|-------------|
| **AA** | Analyse-Agent | Führt Marktanalysen durch, erstellt Snapshots und Signale. Führt **keine** Trades aus. |
| **BA** | Ausführungs-Agent (Broker Agent) | Empfängt Signale vom AA und führt Trades beim Broker aus. |
| **GA** | System-Agent (Guardian Agent) | Überwacht das System, führt übergeordnete Verwaltungsaufgaben aus. |

#### Broker

Das Broker-Modul, mit dem dieser Agent verknüpft ist (z. B. `OXS_T`, `OXS_L`). AA-Agents benötigen den Broker für Kerzen-Daten und Kontoinfos. BA-Agents benötigen ihn zusätzlich für die Trade-Ausführung.

#### LLM

Das LLM-Modul, das dieser Agent für seine Analysen verwendet (z. B. `azure_azmin`). Für AA-Agents und ggf. GA-Agents relevant. BA-Agents in der Standardkonfiguration führen keine eigenständigen LLM-Analysen durch.

#### Pair

Das Währungspaar, auf das sich der Agent konzentriert (z. B. `EUR_USD`, `GBP_USD`, `USD_JPY`).

#### Aufgabe

Eine kurze Beschreibung der spezifischen Aufgabe des Agents. Die Aufgaben-Bezeichnung ist frei konfigurierbar, z. B. `Analyse`, `Trading`, `Monitoring`, `RiskGuard`.

### 4.2 Sortierung

Die Tabelle kann nach jeder Spalte sortiert werden. Ein Klick auf den Spaltenkopf sortiert aufsteigend, ein weiterer Klick absteigend.

### 4.3 Klick auf einen Agent

Ein Klick auf eine Agent-Zeile öffnet die **Chat**-Seite für diesen Agent, wo Sie den Agent direkt befragen oder einen manuellen Analyse-Zyklus starten können.

---

## 5. Agent-Typen im Detail

### 5.1 AA — Analyse-Agent

Der **Analyse-Agent (AA)** ist das analytische Herzstück von OpenForexAI.

**Aufgaben:**
- Abrufen aktueller Kerzen-Daten vom Broker (M5, M15, H1 usw.)
- Berechnung technischer Indikatoren (EMA, SMA, RSI, ATR, Bollinger Bands, VWAP, Swing Levels usw.)
- Aufbau eines strukturierten Analyse-Snapshots (Marktdaten + Indikatoren + Kontext)
- Senden des Snapshots an das LLM zur Interpretation und Entscheidungsfindung
- Auswertung der LLM-Antwort und Extraktion der Handelsentscheidung
- Generierung eines strukturierten Signals: `BUY`, `SELL` oder `HOLD` mit Konfidenzwert, Entry, SL, TP
- Weitergabe des Signals an den verknüpften BA-Agent via Event Bus
- Speicherung des Decision-Snapshots in der Datenbank für spätere Analyse im Orderbook

**Was ein AA-Agent NICHT tut:**
- Er öffnet oder schließt keine Trades.
- Er interagiert nicht direkt mit dem Broker für Ausführungen.
- Er verändert keine offenen Positionen.
- Er trifft keine Entscheidungen über Positionsgrößen (das ist Aufgabe des BA).

**Typischer Zyklus eines AA-Agents:**

```
M5-Kerzen-Trigger empfangen
  → Session-Filter prüfen (Handelszeiten aktiv?)
  → Kerzen-Daten laden (M5, M15, H1)
  → Indikatoren berechnen
  → Swing Levels berechnen
  → Snapshot aufbauen
  → LLM-Anfrage über Event Bus senden
  → LLM-Antwort empfangen
  → Entscheidung extrahieren und validieren
  → Signal generieren (BUY/SELL/HOLD)
  → Signal an BA-Agent senden (Event Bus)
  → Decision-Snapshot in DB speichern
```

### 5.2 BA — Ausführungs-Agent (Broker Agent)

Der **Ausführungs-Agent (BA)** ist für die Umsetzung von Handelssignalen in echte Broker-Aufträge zuständig.

**Aufgaben:**
- Empfang von Handelssignalen vom verknüpften AA-Agent via Event Bus
- Validierung des Signals (Risikoprüfung, Kontoguthaben-Prüfung, Duplikat-Prüfung)
- Berechnung der Positionsgröße basierend auf Risikoprofil und konfiguriertem Einsatz-Prozentsatz
- Berechnung des finalen Stop-Loss und Take-Profit
- Ausführung des Marktauftrags beim Broker via API
- Speicherung des Trade-Eintrags in der lokalen Datenbank
- Überwachung der offenen Position (Sync-Checks)
- Erkennen und Reagieren auf SYNC_DETECTED-Situationen (z. B. extern geschlossene Position)

**Was ein BA-Agent NICHT tut:**
- Er führt keine eigenständige Marktanalyse durch.
- Er trifft keine unabhängigen Handelsentscheidungen.
- Er führt in der Standardkonfiguration keine LLM-Anfragen durch.

**Inspector im Chat:**
Da der BA-Agent kein Chart-basiertes Analyse-Interface hat, zeigt der Chat-Inspector für BA-Agents nur das **Text-Inspector-Panel** ohne Kerzen-Chart. Alle relevanten Informationen (empfangenes Signal, Broker-Response, Positions-Status) werden als Text dargestellt.

### 5.3 GA — System-Agent (Guardian Agent)

Der **System-Agent (GA)** führt übergeordnete Systemaufgaben aus, die keinem einzelnen Währungspaar zugeordnet sind.

**Typische Aufgaben:**
- Globales Risikomanagement (z. B. maximaler täglicher Verlust überschritten → alle Trades stoppen)
- Positionsüberwachung über alle Broker und Paare hinweg
- Systemweite Synchronisation und Konsistenzprüfungen
- Benachrichtigungen und Systemwarnungen generieren

GA-Agents sind optional und nicht in jeder Konfiguration vorhanden. Sie erscheinen in der Agents-Tabelle wenn konfiguriert.

---

## 6. Praktische Workflows

### 6.1 Tägliche Systemprüfung

**Empfohlene Morgenroutine (vor Handelsbeginn):**

**Schritt 1: Initial-Seite öffnen**
Erster Blick auf den Gesamtzustand des Systems.

**Schritt 2: Versionsbereich prüfen**
- Stimmt die lokale Version mit der Internet-Version überein?
- Falls nicht: Update in Betracht ziehen (außerhalb der Haupthandelszeiten).
- Ist der System-Status aktiv (nicht SUSPENDED oder ERROR)?

**Schritt 3: LLM-Schnittstellen prüfen**
- Alle LLM-Module mit grünem „VERBUNDEN"-Badge?
- Falls ein Modul getrennt ist: Vor Handelsbeginn beheben.
- Kurzer Test via Agent Chat: Execute-Lauf durchführen und prüfen, ob eine Antwort kommt.

**Schritt 4: Broker-Schnittstellen prüfen**
- Alle benötigten Broker-Module verbunden und synchronisiert?
- Keine offenen SYNC-FEHLER?

**Schritt 5: Agents-Tabelle prüfen**
- Alle Agents im Status IDLE? (Das ist der erwartete Ruhezustand zwischen Kerzen-Triggern.)
- Kein Agent im Status ERROR?
- Sind alle erwarteten Agents vorhanden und aktiv (nicht DISABLED)?

**Schritt 6: Kurzer Blick in den Monitor**
- Gibt es ungewöhnliche Fehler-Ereignisse aus der letzten Nacht?
- Kommen neue M5-Kerzen-Events an? (Data Events Tab → `m5_candle_update`)
- Werden Agents korrekt getriggert? (Core Events Tab → `agent_trigger_received`)

**Schritt 7: Orderbook prüfen**
- Gibt es unerwartete offene Positionen?
- Wurden über Nacht Trades korrekt geschlossen?
- Gibt es Einträge mit SYNC-Fehlern oder fehlenden Broker-IDs?

### 6.2 Sicheres Pausieren für Konfigurationsänderungen

Wenn Sie Konfigurationsänderungen vornehmen möchten (neue Agents, andere LLM-Parameter, Risiko-Einstellungen, neue Prompts), gehen Sie so vor:

1. **Suspend klicken** — Alle Agent-Zyklen werden pausiert. Das orangefarbene SUSPENDED-Badge erscheint.
2. **Warten**, bis alle laufenden Agents ihren aktuellen Zyklus abgeschlossen haben. Im Monitor: keine neuen RUNNING-Ereignisse.
3. **Konfigurationsänderungen vornehmen** in `system.json5` oder über die Konfigurations-UI.
4. **Änderungen speichern.**
5. **Restart Now klicken** — Damit die neuen Konfigurationen geladen werden.
6. **Warten**, bis der Neustart abgeschlossen ist (alle Verbindungen wieder grün, Agents im IDLE-Status).
7. **Initial-Seite erneut prüfen** — Sind alle Agents korrekt initialisiert? Entspricht die Agents-Tabelle der neuen Konfiguration?
8. Das System startet nach einem Restart automatisch wieder — kein manuelles Continue notwendig.

**Wichtig:** Suspend pausiert nur die Agent-Zyklen. Offene Trades beim Broker bleiben aktiv. Stop-Loss und Take-Profit, die beim Broker hinterlegt sind, greifen weiterhin. Wenn Sie Trades vollständig schützen möchten, schließen Sie diese manuell über den Broker bevor Sie Konfigurationsänderungen vornehmen.

### 6.3 Update-Prozedur

**Schritt-für-Schritt Update:**

1. **Initial-Seite öffnen** — Prüfen, ob die Internet-Version höher als die lokale Version ist.
2. **Release Notes lesen** (optional, aber empfohlen) — Was hat sich geändert? Gibt es breaking changes?
3. **Orderbook prüfen** — Gibt es offene Positionen? Sind diese während des Updates sicher (SL/TP beim Broker bleiben aktiv)?
4. **Suspend klicken** — Alle Agent-Zyklen pausieren.
5. **Warten**, bis keine Agents mehr den Status RUNNING haben.
6. **Update-Button klicken** — Download und Installation starten. Ein Fortschrittsindikator zeigt den Stand an.
7. **Download-Abschluss abwarten.**
8. **Restart Now klicken** — Runtime mit neuer Version starten.
9. **Warten** auf vollständige Initialisierung (10–30 Sekunden).
10. **Versionen prüfen** — Lokale Version sollte jetzt der Internet-Version entsprechen.
11. **LLM und Broker prüfen** — Alle Verbindungen wieder aktiv?
12. **Agents-Tabelle prüfen** — Alle Agents korrekt gestartet?
13. Das System ist nach dem Neustart automatisch aktiv. Kein manuelles Continue notwendig.

**Nach dem Update:** Führen Sie einen Test-Execute-Lauf im Agent Chat durch, um sicherzustellen, dass die neue Version korrekt funktioniert, bevor der reguläre Handel beginnt.

### 6.4 Reaktion auf Verbindungsabbrüche

#### LLM-Verbindungsabbruch

Symptome:
- LLM-Badge wechselt auf ROT oder VERBINDEN…
- Agents bleiben im Status WAITING oder ERROR.
- Im Monitor (LLM Events Tab): `llm_request` ohne nachfolgende `llm_response`, oder `llm_error`-Events.

Maßnahmen:
1. Prüfen Sie Ihre Internetverbindung.
2. Prüfen Sie den Azure/OpenAI/Anthropic-Dienststatus.
3. Versuchen Sie **Restart Now** — oft reicht das, um die Verbindung neu aufzubauen.
4. Falls das Problem anhält: Prüfen Sie API-Key und Endpunkt in der Konfiguration (`system.json5`, Abschnitt `llm_modules`).
5. Als temporäre Lösung: **Suspend** klicken, bis das LLM-Problem behoben ist, um endlose Fehler-Zyklen zu vermeiden.

#### Broker-Verbindungsabbruch

Symptome:
- Broker-Badge wechselt auf ROT oder RECONNECTING.
- BA-Agents können keine Trades ausführen — Events im Monitor zeigen Broker-Fehler.
- Im Monitor (Broker Events Tab): `broker_disconnected`-Event, gefolgt von `broker_reconnecting`.

Maßnahmen:
1. Prüfen Sie Ihre Internetverbindung.
2. Prüfen Sie den Status der Broker-API-Plattform (z. B. OANDA-Status-Seite).
3. Warten Sie auf den automatischen Reconnect-Versuch (erkennbar am RECONNECTING-Badge). Das System versucht automatisch, die Verbindung wiederherzustellen.
4. Falls kein automatischer Reconnect erfolgreich ist: **Restart Now** klicken.
5. Nach Wiederherstellung: Im Orderbook prüfen, ob alle offenen Positionen korrekt synchronisiert sind. Achten Sie auf Einträge ohne Broker-ID oder mit Sync-Warnungen.

**Kritisch bei Broker-Abbruch mit offenen Positionen:**
Offene Positionen beim Broker sind durch die dort hinterlegten SL/TP-Orders geschützt, auch wenn OpenForexAI keine Verbindung hat. Sobald die Verbindung wiederhergestellt ist, synchronisiert das System den aktuellen Zustand aller Positionen. Im Orderbook erscheint dann ggf. der Schließgrund `SYNC_DETECTED`, wenn eine Position extern (durch SL/TP beim Broker) geschlossen wurde.

#### Kompletter Systemabbruch

Falls das System komplett abstürzt oder die Verbindung zum Frontend verloren geht:

1. Die Runtime läuft möglicherweise noch im Hintergrund als Node.js-Prozess. Prüfen Sie den Prozessstatus.
2. Öffnen Sie das Frontend neu (Browser-Refresh oder App neu starten).
3. Falls die Runtime nicht mehr läuft: Neu starten via Terminal mit dem konfigurierten Start-Befehl.
4. Nach dem Neustart: Initial-Seite prüfen, alle Verbindungen verifizieren, Orderbook auf fehlende Synchronisierungen prüfen.

---

## 7. Status-Übersicht auf einen Blick

Die Initial-Seite ist so gestaltet, dass der Gesamtzustand in wenigen Sekunden erfasst werden kann:

| Element | Alles OK | Handlungsbedarf |
|---------|----------|-----------------|
| Versionsbereich | Lokal = Internet | Lokal < Internet (Update verfügbar) |
| System-Status | RUNNING (aktiv) | SUSPENDED (wenn unerwartet), ERROR |
| LLM-Module | Alle grün VERBUNDEN | Ein oder mehrere rot GETRENNT |
| Broker-Module | Alle grün VERBUNDEN + SYNC | Ein oder mehrere rot oder SYNC-FEHLER |
| Agents-Tabelle | Alle IDLE oder RUNNING | ERROR, DISABLED (unerwartet), fehlende Agents |

Ein vollständig gesundes System zeigt alle grünen Badges und alle Agents im IDLE- oder RUNNING-Zustand. Jede Abweichung davon sollte untersucht werden, bevor der Handelstag beginnt.

---

## 8. Häufige Fragen

**F: Was bedeutet es, wenn ein Agent den Status IDLE hat, aber keine Trades kommen?**

A: IDLE ist der normale Ruhezustand zwischen Kerzen-Triggern. Ob Trades kommen, hängt von der LLM-Analyse ab. IDLE bedeutet nur, dass der Agent betriebsbereit ist und auf den nächsten M5-Trigger wartet. Auch wenn Analysen laufen, gibt das LLM möglicherweise HOLD zurück — dann werden keine Trades ausgeführt.

**F: Kann ich einzelne Agents pausieren, ohne das gesamte System zu suspendieren?**

A: In der Standard-UI ist Suspend ein systemweiter Befehl. Einzelne Agents können über die Konfigurationsdatei deaktiviert werden (dann erscheinen sie als DISABLED in der Tabelle), was aber einen Restart erfordert.

**F: Was passiert mit offenen Trades, wenn ich Restart Now drücke?**

A: Offene Trades beim Broker sind durch die dort hinterlegten SL/TP-Orders geschützt und bleiben aktiv. Nach dem Neustart synchronisiert das System den aktuellen Zustand aller Positionen. In der Regel gibt es keine Unterbrechung des Handelschutzes durch SL/TP.

**F: Wie oft sollte ich die Initial-Seite prüfen?**

A: Empfohlen wird eine Prüfung am Morgen vor Handelsbeginn. Das Monitor-Panel zeigt Probleme in Echtzeit, aber die Initial-Seite gibt die schnellste strukturierte Übersicht über den Systemzustand.

**F: Die Internet-Version ist höher, aber ich möchte noch nicht updaten. Was tun?**

A: Ignorieren Sie das Update-Badge und klicken Sie den Update-Button nicht. Das System läuft weiterhin mit der aktuellen lokalen Version. Es gibt keine automatischen Updates ohne Ihre Bestätigung.

**F: Der Status eines Agents steht auf ERROR. Was tun?**

A: Öffnen Sie den Monitor-Tab und wechseln Sie zu „All Events" oder „Core Events". Suchen Sie nach Fehler-Events des betreffenden Agents. Häufige Ursachen: LLM-Verbindungsfehler, fehlerhafter Snapshot-Aufbau, Broker-API-Fehler, Konfigurationsfehler. Nach Behebung der Ursache hilft oft ein **Restart Now**.

**F: Was bedeutet der Schließgrund SYNC_DETECTED im Orderbook?**

A: SYNC_DETECTED bedeutet, dass OpenForexAI beim nächsten Sync-Check festgestellt hat, dass eine Position beim Broker nicht mehr existiert — sie wurde außerhalb von OpenForexAI geschlossen (z. B. durch SL/TP beim Broker, oder manuell). Das System hat die Position daraufhin in der lokalen Datenbank als geschlossen markiert.
