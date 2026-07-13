[Zurück zu Action](ui.action.de.md)

# Agent Chat — Handbuch

Der **Agent Chat** ist die interaktive Kommunikationsoberfläche für jeden konfigurierten Agent. Er dient zwei unterschiedlichen Zwecken: dem direkten Gespräch mit dem LLM (über **Send**) und dem Starten eines vollständigen Analyse-Zyklus im kontrollierten Inspect-Modus (über **Execute**). Der Agent Chat ist das wichtigste Werkzeug zum Verstehen, Testen und Debuggen des Agenten-Verhaltens.

Die Seite ist in zwei Hauptbereiche aufgeteilt:
- **Linkes Panel** — Steuerung, Eingabe, Chat-Verlauf
- **Rechtes Panel** — Chart und Inspector (nur bei AA-Agents)

---

## 1. Linkes Panel

### 1.1 Agent-Dropdown

Das **Agent-Dropdown** befindet sich oben links und zeigt alle konfigurierten Agents als auswählbare Einträge. Jeder Agent wird mit seiner ID angezeigt (z. B. `OXS_T-EURUSD-AA-ANLYS`).

**Wichtige Hinweise:**
- Nach dem Wechsel des Agents wird der Chat-Verlauf des vorherigen Agents ausgeblendet und der Verlauf des neuen Agents geladen.
- Der gewählte Agent bestimmt, was im rechten Panel angezeigt wird: AA-Agents zeigen Chart + Inspector, BA-Agents zeigen nur den Text-Inspector.
- Der zuletzt gewählte Agent wird beim nächsten Öffnen der Seite wiederhergestellt.

### 1.2 Timeout-Feld

Das **Timeout-Feld** erlaubt die Konfiguration des maximalen Wartezeitraums für eine Antwort auf Execute- oder Send-Operationen. Der Wert wird in Sekunden angegeben.

- **Bereich:** 5 bis 300 Sekunden
- **Standard:** 60 Sekunden (je nach Konfiguration)
- **Verwendung:** Bei großen Analyse-Zyklen mit vielen Tool-Aufrufen oder langsamen LLM-Diensten kann der Timeout erhöht werden. Bei schnellen lokalen Modellen kann er reduziert werden.

Wenn ein Execute oder Send den Timeout überschreitet, wird die Operation mit einer Fehlermeldung beendet und im Chat-Verlauf als fehlgeschlagen markiert. Im Monitor ist ein entsprechendes Fehler-Event sichtbar.

### 1.3 Anweisungs-Textfeld

Das **Anweisungs-Textfeld** (auch: Instruktions-Feld) enthält die Nachrichten oder Anweisungen, die an den Agent gesendet werden. Es ist mehrzeilig und unterstützt längere Texte.

**Verwendung für Send:**
Geben Sie eine direkte Frage oder Anweisung ein, die ohne Kontext oder Analyse-Zyklus direkt an das LLM weitergeleitet wird. Beispiel:
```
Was sind die wichtigsten Faktoren für eine zuverlässige Unterstützungslinie?
```

**Verwendung für Execute:**
Das Textfeld kann bei Execute als zusätzliche Anweisung oder Kontext verwendet werden, der zusammen mit dem Analyse-Snapshot an das LLM gesendet wird. Bei vielen Konfigurationen wird das Feld bei Execute ignoriert oder als optionaler Zusatz-Kontext behandelt.

**Verwendung für BA-Agents:**
Bei BA-Agents kann ein vollständiges AA-Analyse-Ergebnis (kopiert aus dem Chat-Verlauf oder dem Inspector-Tab eines AA-Agents) in das Textfeld eingefügt werden. Ein Execute-Lauf führt dann die Trade-Entscheidungslogik des BA-Agents mit diesem Eingabe-Signal durch — ideal zum Testen der BA-Logik mit kontrollierten Eingaben.

### 1.4 Speichern-Button

Der **Speichern-Button** neben dem Anweisungs-Textfeld speichert den aktuellen Inhalt des Textfelds als persistierte Anweisung für diesen Agent.

- Die gespeicherte Anweisung wird beim nächsten Öffnen des Agent Chats für diesen Agent automatisch geladen.
- Dies ist nützlich für häufig verwendete Test-Prompts oder Standard-Anweisungen, die bei jedem Execute-Lauf als Kontext mitgesendet werden sollen.
- Zum Löschen der gespeicherten Anweisung: Textfeld leeren und Speichern klicken.

### 1.5 Chat-Verlauf

Der **Chat-Verlauf** zeigt alle bisherigen Nachrichten und Antworten für den gewählten Agent in chronologischer Reihenfolge.

**Nachrichten-Typen im Verlauf:**

| Typ | Darstellung | Beschreibung |
|-----|-------------|-------------|
| Benutzer-Nachricht | Rechts ausgerichtet, blau/grau | Ihre gesendete Anweisung (Send) |
| LLM-Antwort | Links ausgerichtet, weiß/hell | Direkte Antwort des LLM (bei Send) |
| Execute-Ergebnis | Links ausgerichtet, strukturiert | Vollständiges Analyse-Ergebnis mit Decision, Confidence, Signal |
| Fehler | Rot markiert | Timeout, LLM-Fehler, Verbindungsfehler |
| System-Nachricht | Grau, kursiv | Systemhinweise (Agent gestartet, Timeout-Änderung usw.) |

**Kopier-Buttons:**
Neben jeder Antwort im Chat-Verlauf befindet sich ein **Kopier-Button** (Clipboard-Icon). Ein Klick kopiert den vollständigen Text der Antwort in die Zwischenablage.

Dies ist besonders nützlich, um:
- Ein AA-Analyse-Ergebnis zu kopieren und in den Chat eines BA-Agents einzufügen (für BA-Testing).
- Ein interessantes LLM-Ergebnis zur weiteren Verwendung zu sichern.
- Fehler-Details für die Fehlersuche zu extrahieren.

**Scroll-Verhalten:**
Der Chat-Verlauf scrollt automatisch zur neuesten Nachricht, wenn eine neue Antwort eintrifft. Bei manuellem Hochscrollen wird das automatische Scrollen vorübergehend deaktiviert.

### 1.6 Execute-Button

Der **Execute**-Button startet einen vollständigen Analyse-Zyklus für den gewählten Agent im **Inspect-Modus**.

**Was Execute genau tut:**

1. Der Agent-Zyklus wird manuell ausgelöst — unabhängig vom normalen M5-Kerzen-Trigger.
2. Der Agent durchläuft seinen kompletten Zyklus:
   - Kerzen-Daten laden
   - Indikatoren berechnen
   - Snapshot aufbauen
   - LLM-Anfrage senden
   - LLM-Antwort empfangen und verarbeiten
   - Entscheidung extrahieren
3. Das Ergebnis erscheint im Chat-Verlauf als strukturierte Ausgabe.
4. **Im Inspect-Modus werden KEINE echten Signale an BA-Agents weitergeleitet.** Die Analyse wird vollständig durchgeführt, aber das Signal bleibt im Chat-Kontext.
5. Der Inspector rechts (bei AA-Agents) zeigt alle technischen Details des Zyklus.

**Wann Execute verwenden:**
- Um zu prüfen, wie der Agent auf die aktuellen Marktbedingungen reagiert, ohne einen echten Trade auszulösen.
- Um nach Konfigurationsänderungen (z. B. neuer Prompt) zu testen, ob die Analyse korrekt funktioniert.
- Um den Snapshot zu inspizieren, der an das LLM gesendet wird.
- Um die LLM-Antwort und die extrahierte Entscheidung zu überprüfen.
- Zur Fehlersuche: Warum gibt der Agent kein Signal? Welche Daten sieht er?

**Execute bei BA-Agents:**
Bei BA-Agents führt Execute den Trade-Entscheidungsprozess mit dem Inhalt des Textfelds als Input-Signal durch. Dies ist nützlich zum Testen der BA-Logik (Positionsgrößenberechnung, Risikoprüfung, Signal-Validierung) ohne ein echtes AA-Signal abzuwarten. Auch bei BA-Execute werden KEINE echten Trades ausgeführt.

### 1.7 Send-Button

Der **Send**-Button sendet den Inhalt des Textfelds als direkte Frage oder Anweisung an das LLM des gewählten Agents.

**Unterschied zu Execute:**

| Aspekt | Send | Execute |
|--------|------|---------|
| Analyse-Zyklus | Kein vollständiger Zyklus | Vollständiger Zyklus (Kerzen laden, Indikatoren, Snapshot) |
| Kontext | Nur der eingegebene Text | Aktueller Markt-Snapshot + eingegebener Text (optional) |
| Signal-Generierung | Nein | Ja (aber nur im Inspect-Modus, kein echtes Signal) |
| Inspector-Update | Nein | Ja — alle Tabs werden mit neuen Daten befüllt |
| Verwendung | Allgemeine Fragen, Erklärungen, Tests | Vollständige Analyse-Simulation |
| LLM-Tokens | Wenig (nur Ihre Frage + System-Prompt) | Viele (kompletter Snapshot + System-Prompt + Indikatoren) |

**Typische Send-Verwendungen:**
```
Erkläre mir, wie du eine Handelsentscheidung bei einem starken Aufwärtstrend triffst.
```
```
Was ist dein aktuelles Verständnis von EURUSD basierend auf den letzten 24 Stunden?
```
```
Wenn der RSI bei 72 liegt und der Preis die obere Bollinger Band berührt, was würdest du empfehlen?
```

Send ist auch nützlich, um zu prüfen, ob das LLM überhaupt erreichbar ist — eine kurze Frage wie „Hallo?" zeigt sofort, ob die LLM-Verbindung funktioniert.

### 1.8 Chat löschen

Der **Chat löschen**-Button entfernt den gesamten sichtbaren Chat-Verlauf für den aktuell gewählten Agent.

**Wichtig:** Das Löschen des Chats entfernt nur die Anzeige im Frontend. Die Analyse-Ergebnisse und Decision-Snapshots, die in der Datenbank gespeichert sind, bleiben erhalten und sind weiterhin im Orderbook und im Chart-Analyse-Analyst einsehbar.

Der Chat-Verlauf wird serverseitig nicht dauerhaft gespeichert — ein Reload der Seite oder ein Restart löscht den Verlauf ebenfalls.

### 1.9 Export .md

Der **Export .md**-Button exportiert den gesamten sichtbaren Chat-Verlauf als **Markdown-Datei** in den Download-Ordner des Browsers.

Die exportierte Datei enthält:
- Zeitstempel aller Nachrichten
- Vollständige Texte aller Benutzer-Nachrichten und LLM-Antworten
- Execute-Ergebnisse mit strukturierten Entscheidungen
- Fehlermeldungen (falls vorhanden)

Der Export ist nützlich für:
- Dokumentation interessanter Analyse-Ergebnisse
- Weitergabe von Test-Ergebnissen an andere
- Archivierung eines langen Debug-Sessions
- Vergleich von Analyse-Ergebnissen über Zeit

---

## 2. Rechtes Panel — AA-Agents

Das rechte Panel ist nur für **AA-Agents** (Analyse-Agents) vollständig ausgestattet. Es zeigt einen interaktiven Kerzen-Chart und darunter den **Inspector** mit mehreren Tabs.

### 2.1 Kerzen-Chart

Der Kerzen-Chart zeigt die aktuellen Marktdaten für das Währungspaar des gewählten Agents.

**Eigenschaften des Charts:**
- Zeigt OHLCV-Kerzen (Open, High, Low, Close, Volume)
- Unterstützt Indikatoren als Overlays (EMA, SMA) und Oszillatoren (RSI, ATR) in separaten Panels darunter
- Zeigt Analyse-Marker für vergangene Execute-Läufe (sofern aktiviert)
- Interaktiv: Mausrad zum Zoomen, Ziehen zum Verschieben

**Manueller Refresh-Button:**
Der Chart im Agent Chat hat einen **manuellen Refresh-Button** — er aktualisiert sich **nicht** automatisch. Dies ist eine bewusste Designentscheidung:

- Kein Auto-Polling vermeidet unerwartete Datennachladen während eines aktiven Execute-Laufs.
- Der Benutzer hat volle Kontrolle darüber, wann neue Daten geladen werden.
- Nach einem Execute-Lauf kann der Chart manuell aktualisiert werden, um die neuesten Kerzen zu sehen.

**Wann Refresh klicken:**
- Nach dem Öffnen des Agent Chats für einen neuen Agent
- Bevor ein Execute-Lauf, um sicherzustellen, dass der Chart die aktuellen Daten zeigt
- Wenn Sie wissen möchten, ob neue Kerzen seit dem letzten Refresh eingetroffen sind

### 2.2 Timeframe-Buttons

Die **Timeframe-Buttons** (M5 · M15 · H1) wechseln den angezeigten Zeitrahmen des Charts.

- **M5** — 5-Minuten-Kerzen. Zeigt kurzfristige Preisbewegungen und ist der primäre Trigger-Timeframe.
- **M15** — 15-Minuten-Kerzen. Zeigt mittelfristige Strukturen.
- **H1** — 1-Stunden-Kerzen. Zeigt den übergeordneten Trend.

Je nach Konfiguration können weitere Timeframes (M30, H4, D1) verfügbar sein.

**Hinweis:** Der Wechsel des Timeframes lädt automatisch neue Kerzen vom Broker nach.

### 2.3 Indikatoren hinzufügen

Über die Indikator-Steuerelemente können Indikatoren zum Chart hinzugefügt werden:

- **EMA** (Exponentieller Gleitender Durchschnitt) — als Overlay-Linie auf dem Kerzen-Chart
- **SMA** (Einfacher Gleitender Durchschnitt) — als Overlay-Linie
- **RSI** (Relative Stärke Index) — als Oszillator in separatem Panel
- **ATR** (Average True Range) — als Volatilitäts-Oszillator

Pro Indikator können Periode und Timeframe eingestellt werden. Mehrere Instanzen desselben Typs (z. B. EMA 20 und EMA 50) sind möglich.

Die Indikator-Einstellungen im Agent Chat sind unabhängig von denen in der Chart-Analyse-Seite.

---

## 3. Inspector-Tabs (AA-Agents)

Der **Inspector** befindet sich unterhalb des Charts im rechten Panel. Er zeigt die technischen Details des zuletzt durchgeführten Execute-Laufs. Die Tabs werden nach einem Execute-Lauf automatisch mit neuen Daten befüllt.

### 3.1 Tab: Übersicht (Overview)

Der **Übersicht-Tab** zeigt eine strukturierte Zusammenfassung des letzten Execute-Laufs:

- **Agent-ID** und **Timestamp** des Laufs
- **Decision** — die getroffene Entscheidung (BUY, SELL, HOLD) mit Konfidenzwert (0–100%)
- **Entry Price** — der empfohlene Einstiegspreis
- **Stop Loss** — der empfohlene Stop-Loss-Level
- **Take Profit** — der empfohlene Take-Profit-Level
- **Risk/Reward Ratio** — berechnetes Chance-Risiko-Verhältnis
- **Reasoning** — kurze Begründung der Entscheidung (aus LLM-Antwort extrahiert)
- **Laufzeit** — wie lange der gesamte Zyklus gedauert hat (in Millisekunden)
- **Token-Verbrauch** — Anzahl der verwendeten Input- und Output-Tokens

Dieser Tab gibt den schnellsten Überblick über das Analyse-Ergebnis ohne in die technischen Details einzutauchen.

### 3.2 Tab: Snapshot

Der **Snapshot-Tab** zeigt den vollständigen **Analyse-Snapshot**, der an das LLM gesendet wurde.

Ein Snapshot ist eine strukturierte JSON-Darstellung aller Marktdaten zum Zeitpunkt der Analyse:

```json
{
  "pair": "EUR_USD",
  "timestamp": "2026-06-03T08:35:00Z",
  "timeframe": "M5",
  "candles": {
    "M5": [...],
    "M15": [...],
    "H1": [...]
  },
  "indicators": {
    "ema_20_M5": 1.08542,
    "ema_50_M5": 1.08498,
    "rsi_14_M5": 58.3,
    "atr_14_M5": 0.00087
  },
  "swing_levels": {
    "resistance": [1.08720, 1.08850],
    "support": [1.08320, 1.08150]
  },
  "account": {
    "balance": 10000.00,
    "open_positions": 0
  }
}
```

**Wozu der Snapshot-Tab nützlich ist:**
- Prüfen, ob alle erwarteten Daten (Kerzen, Indikatoren, Swing Levels) korrekt im Snapshot vorhanden sind.
- Verifizieren, ob die Indikatorwerte plausibel sind.
- Fehlende oder fehlerhafte Daten identifizieren, die zu falschen LLM-Entscheidungen führen könnten.
- Den Snapshot kopieren (Kopier-Button) und manuell analysieren.

Wenn der Snapshot leer oder fehlerhaft ist, ist das oft ein Hinweis auf Konfigurations- oder Daten-Pipeline-Probleme.

### 3.3 Tab: LLM

Der **LLM-Tab** zeigt die vollständige LLM-Kommunikation des letzten Execute-Laufs:

**LLM Input (System-Prompt + User-Message):**
Der vollständige Text, der an das LLM gesendet wurde, einschließlich:
- System-Prompt (konfigurierter Analyse-Prompt)
- Formatierter Snapshot als Benutzer-Nachricht
- Optionale zusätzliche Anweisungen aus dem Textfeld

**LLM Output (Raw Response):**
Die vollständige, unverarbeitete Antwort des LLM. Dies ist der Rohtext vor der JSON-Extraktion.

**Extrahierte Decision:**
Das strukturierte JSON-Objekt, das aus der LLM-Antwort extrahiert wurde.

**Token-Details:**
- Input-Tokens (Anzahl der Tokens im gesendeten Prompt)
- Output-Tokens (Anzahl der Tokens in der LLM-Antwort)
- Gesamtkosten-Schätzung (wenn konfiguriert)
- Verarbeitungszeit (nur LLM-Latenz)

**Wozu der LLM-Tab nützlich ist:**
- Den Prompt-Inhalt prüfen: Wurde der Snapshot korrekt formatiert?
- Die rohe LLM-Antwort vor der Verarbeitung sehen: Was hat das LLM tatsächlich geantwortet?
- Parsing-Probleme erkennen: Konnte die Decision korrekt extrahiert werden?
- Token-Verbrauch optimieren: Welche Teile des Prompts sind besonders groß?
- Prompt-Engineering: Verstehen, wie der aktuelle Prompt auf die Marktdaten reagiert.

### 3.4 Tab: Tools

Der **Tools-Tab** zeigt alle **Tool-Aufrufe**, die während des Execute-Laufs stattgefunden haben.

In OpenForexAI können Agents Tool-Funktionen aufrufen (z. B. spezifische Daten-Abfragen, erweiterte Berechnungen). Der Tools-Tab zeigt:

- **Tool-Name** — welche Tool-Funktion aufgerufen wurde
- **Input-Parameter** — die übergebenen Parameter
- **Output/Ergebnis** — das zurückgegebene Ergebnis
- **Ausführungszeit** — wie lange der Tool-Aufruf gedauert hat
- **Status** — Erfolg oder Fehler

**Typische Tools:**
- `get_candles` — Kerzen-Daten abrufen
- `calculate_indicator` — Indikatoren berechnen
- `get_swing_levels` — Swing Levels berechnen
- `get_account_info` — Kontodaten abrufen

**Wozu der Tools-Tab nützlich ist:**
- Prüfen, ob alle Tool-Aufrufe erfolgreich waren.
- Sehen, welche Daten durch Tool-Aufrufe abgerufen wurden.
- Fehlerhafte Tool-Aufrufe identifizieren (z. B. wenn ein Tool leere Daten zurückgibt).
- Die Ausführungszeit einzelner Tool-Aufrufe analysieren.

### 3.5 Tab: Runtime

Der **Runtime-Tab** zeigt Laufzeit- und Diagnose-Informationen des Execute-Laufs:

- **Gesamt-Laufzeit** — Ende-zu-Ende-Zeit des gesamten Zyklus
- **Phase-Zeiten** — Aufschlüsselung nach Phasen (Daten laden, Snapshot aufbauen, LLM-Aufruf, Verarbeitung)
- **Speicher-Nutzung** (wenn verfügbar)
- **Fehler und Warnungen** — alle aufgetretenen nicht-kritischen Probleme
- **Agent-Konfiguration** — aktuell aktive Konfigurationsparameter des Agents
- **Session-Filter-Status** — war der Agent in einer aktiven Handelssession?

**Wozu der Runtime-Tab nützlich ist:**
- Performance-Engpässe identifizieren (z. B. ein bestimmter Tool-Aufruf dauert sehr lange).
- Warnungen prüfen, die nicht zu einem Fehler geführt haben, aber auf Probleme hinweisen.
- Verstehen, warum ein Zyklus länger als erwartet gedauert hat.

---

## 4. Rechtes Panel — BA-Agents

Für **BA-Agents** (Ausführungs-Agents) zeigt das rechte Panel keinen Kerzen-Chart. Stattdessen gibt es ausschließlich den **Text-Inspector**.

### 4.1 Text-Inspector für BA-Agents

Der Text-Inspector zeigt bei einem Execute-Lauf für BA-Agents:

- **Empfangenes Signal** — das Signal, das als Input verarbeitet wurde (aus dem Textfeld oder einem echten AA-Signal)
- **Validierungs-Ergebnis** — wurde das Signal als gültig eingestuft?
- **Positionsgrößen-Berechnung** — wie wurde die Einheitenzahl berechnet
- **Risiko-Bewertung** — Einsatz in % des Kontoguthabens, Risiko-Betrag
- **SL/TP-Berechnung** — finaler Stop-Loss und Take-Profit
- **Broker-Auftrag** (nur bei realem Signal, nicht bei Execute-Inspect) — der gesendete Auftrag und die Broker-Antwort

Im Execute-Modus (Inspect) werden KEINE echten Trades ausgeführt. Der BA-Agent zeigt nur, was er tun würde.

---

## 5. Unterschied Execute vs. Send — Entscheidungshilfe

| Frage | Execute | Send |
|-------|---------|------|
| Ich möchte sehen, ob die Analyse mit aktuellen Marktdaten funktioniert | ✓ | — |
| Ich möchte den Snapshot prüfen, der an das LLM geht | ✓ | — |
| Ich möchte eine einfache Frage an das LLM stellen | — | ✓ |
| Ich möchte testen, ob das LLM erreichbar ist | — | ✓ |
| Ich möchte die Tool-Aufrufe des Agents sehen | ✓ | — |
| Ich möchte den Decision-Snapshot für Debug-Zwecke sehen | ✓ | — |
| Ich möchte den Agent etwas über Markttheorie fragen | — | ✓ |
| Ich möchte nach einer Prompt-Änderung testen, ob die Ausgabe stimmt | ✓ | — |
| Ich möchte schnell prüfen, ob die LLM-Verbindung aktiv ist | — | ✓ (schneller) |
| Ich möchte verstehen, warum der Agent kein Signal generiert | ✓ | — |

---

## 6. Praktische Beispiele

### 6.1 Vollständigen Analyse-Zyklus testen

Szenario: Sie haben den System-Prompt geändert und möchten prüfen, ob die neue Konfiguration korrekte Ausgaben liefert.

1. Agent Chat öffnen.
2. AA-Agent für das gewünschte Pair auswählen (z. B. `OXS_T-EURUSD-AA-ANLYS`).
3. **Chart manuell refreshen**, um sicherzustellen, dass aktuelle Kerzen geladen sind.
4. Textfeld leer lassen (oder eine optionale Anweisung eingeben).
5. **Execute** klicken.
6. Auf die Antwort im Chat-Verlauf warten.
7. **LLM-Tab** im Inspector öffnen — prüfen Sie den System-Prompt und die rohe LLM-Antwort.
8. **Snapshot-Tab** öffnen — sind alle erwarteten Daten im Snapshot?
9. **Übersicht-Tab** öffnen — ist die extrahierte Entscheidung plausibel?
10. Bei Problemen: **Tools-Tab** prüfen — gab es fehlerhafte Tool-Aufrufe?

### 6.2 BA-Agent mit AA-Ergebnis testen

Szenario: Sie möchten prüfen, wie der BA-Agent auf ein bestimmtes AA-Signal reagiert.

1. Zuerst den **AA-Agent** im Chat öffnen und einen Execute-Lauf durchführen.
2. Das Ergebnis im Chat-Verlauf per **Kopier-Button** kopieren.
3. Den Agent wechseln zum **BA-Agent** (z. B. `OXS_T-EURUSD-BA-TRADE`).
4. Das kopierte AA-Ergebnis in das **Anweisungs-Textfeld** einfügen.
5. **Execute** klicken.
6. Im Text-Inspector prüfen:
   - Wurde das Signal als gültig erkannt?
   - Wie wurde die Positionsgröße berechnet?
   - Welche SL/TP-Levels wurden berechnet?
7. Da es sich um einen Execute-Inspect-Modus handelt: Kein echter Trade wird ausgeführt.

### 6.3 LLM-Verbindung schnell prüfen

Szenario: Nach einem Netzwerkausfall möchten Sie wissen, ob das LLM wieder erreichbar ist.

1. Agent Chat öffnen, beliebigen AA-Agent wählen.
2. In das Textfeld schreiben: `Bitte antworte mit OK wenn du mich hörst.`
3. **Send** klicken (nicht Execute — das wäre unnötig aufwändig).
4. Wenn innerhalb des Timeouts eine Antwort kommt: LLM-Verbindung funktioniert.
5. Wenn Timeout oder Fehler: LLM-Verbindung prüfen (Initial-Seite → LLM-Badge).

### 6.4 Warum gibt der Agent kein BUY-Signal?

Szenario: Der AA-Agent läuft seit Stunden, aber es wurden keine BUY-Signale generiert. Sie möchten verstehen, was das LLM sieht.

1. Agent Chat öffnen, den betreffenden AA-Agent wählen.
2. Chart refreshen — wie sehen die aktuellen Kerzen aus? Gibt es einen klaren Trend?
3. Timeframe auf H1 wechseln — übergeordneter Trend bullisch oder bearisch?
4. **Execute** klicken.
5. Im Chat-Verlauf: Was ist die aktuelle Decision? HOLD oder SELL?
6. **LLM-Tab** öffnen — rohe LLM-Antwort lesen. Was begründet das LLM seine Entscheidung?
7. **Snapshot-Tab** öffnen — welche Indikatorwerte sieht das LLM? Sind RSI, EMA-Verhältnis, Swing Levels korrekt?
8. Falls die Begründung nachvollziehbar ist: Der Markt bietet gerade keine guten Bedingungen.
9. Falls die Begründung unplausibel wirkt: Prompt-Konfiguration oder Snapshot-Aufbau überprüfen.

### 6.5 Analyse für Dokumentation exportieren

Szenario: Ein besonders interessanter Trade oder eine ungewöhnliche Marktlage — Sie möchten die Analyse dokumentieren.

1. Execute-Lauf durchführen und vollständige Antwort abwarten.
2. **Export .md** klicken — die Datei wird heruntergeladen.
3. Die Markdown-Datei enthält den vollständigen Dialog mit Zeitstempeln.
4. Optional: Zusätzliche Informationen aus dem Inspector (LLM-Tab, Snapshot-Tab) manuell in die Datei einfügen.

---

## 7. Tipps und Best Practices

**Timeout großzügig setzen:** Bei komplexen Analyze-Läufen mit vielen Timeframes und Indikatoren kann ein Execute-Lauf 30–60 Sekunden dauern. Setzen Sie den Timeout auf mindestens 90 Sekunden, um unnötige Timeout-Fehler zu vermeiden.

**Chat regelmäßig löschen:** Ein sehr langer Chat-Verlauf kann die Seite verlangsamen. Löschen Sie den Verlauf nach ausgiebigen Debug-Sessions.

**Inspector-Tabs vor Execute erkunden:** Machen Sie sich mit der Struktur des Snapshots und des LLM-Outputs vertraut, bevor Sie Prompt-Änderungen vornehmen. So verstehen Sie besser, was geändert werden muss.

**Send für schnelle Tests, Execute für gründliche:** Verwenden Sie Send wenn Sie nur eine schnelle Antwort des LLM benötigen. Execute ist für vollständige Analyse-Tests — es lädt Daten, berechnet Indikatoren und beansprucht mehr Zeit und Ressourcen.

**Gespeicherte Anweisung nutzen:** Wenn Sie regelmäßig mit einem bestimmten Test-Szenario arbeiten, speichern Sie die Anweisung über den Speichern-Button. Das spart Zeit bei wiederholten Tests.

**Monitor parallel nutzen:** Beim Ausführen von Execute-Läufen lohnt es sich, den Monitor-Tab in einem zweiten Browser-Fenster offen zu haben. So sehen Sie die Ereignisse in Echtzeit: LLM-Anfragen, Tool-Aufrufe, Antworten.
