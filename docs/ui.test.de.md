[Zurück zum UI-Handbuch](ui.de.md)

# Test

Der Bereich `Test` enthält aktuell:

- [LLM Checker](ui.test.llm_checker.de.md)
- [Tool Executor](ui.test.tool_executor.de.md)

Diese Werkzeuge werden für isolierte Prüfungen verwendet — vor dem Live-Betrieb oder bei der Fehlersuche. Sie sind bewusst vom `Agent Chat`-Execute-Workflow getrennt: Während Agent Chat einen vollständigen Agentenzyklus von Ende zu Ende testet, testen die Test-Tools einzelne Komponenten isoliert.

---

## Wann die Test-Tools eingesetzt werden

Den Test-Bereich verwenden:

- **Vor der ersten Inbetriebnahme**: LLM-Konnektivität und Tool-Verfügbarkeit prüfen, bevor Live-Agenten aktiviert werden
- **Nach Konfigurationsänderungen**: prüfen, dass ein neues LLM-Modul oder eine neue Tool-Konfiguration wie erwartet funktioniert
- **Bei der Fehlersuche**: herausfinden, ob ein Problem vom LLM, einem bestimmten Tool oder der Agentenlogik stammt
- **Beim Schreiben neuer Prompts**: Prompt-Formatierung und LLM-Antwortstruktur testen, bevor sie in ein Decision-Prompt-Profil eingebettet werden
- **Beim Hinzufügen neuer Tools zu einem Snapshot**: prüfen, dass das Tool-Ausgabeformat mit den Erwartungen der Transform-Scripts übereinstimmt

Die Test-Tools lösen keine Agentenzyklen aus, erzeugen keine Handelssignale und interagieren nicht mit dem Broker. Sie können jederzeit sicher verwendet werden — auch während des Live-Handels.

---

## LLM Checker

`LLM Checker` wird verwendet, um eine Nachrichtensequenz direkt an ein konfiguriertes LLM zu senden und die Antwort zu prüfen.

Einsatzbereiche:

- sicherstellen, dass ein LLM-Modul verbunden ist und antwortet
- Prompt-Formatierung testen, bevor sie in ein Agentenprofil eingebettet wird
- Tool-Calling-Verhalten isoliert prüfen
- Token-Kosten für einen bestimmten Prompt schätzen

### Wie LLM Checker funktioniert

LLM Checker ermöglicht:

1. Ein LLM-Modul aus dem Dropdown auswählen
2. Eine Nachrichtensequenz zusammenstellen (System-Message + User-Message)
3. Optional Tool-Definitionen für den Aufruf definieren
4. Anfrage senden und die rohe Antwort prüfen

Die Antwortansicht zeigt:
- den rohen LLM-Ausgabetext
- das strukturierte JSON-Parsing-Ergebnis (wenn die Antwort gültiges JSON ist)
- Token-Verbrauch (Input, Output, gesamt)
- Latenz (Zeit von Anfrage bis Antwort)
- etwaige Fehlermeldungen des LLM-Providers

### Typischer LLM-Checker-Ablauf

**Neuen Decision Prompt testen, bevor er gespeichert wird:**

1. LLM Checker öffnen
2. Das LLM-Modul auswählen, das für den Handel verwendet wird
3. Den Entwurf des System-Prompts in das System-Message-Feld einfügen
4. Ein Beispiel-Snapshot-JSON in das User-Message-Feld einfügen (aus dem Test-Snapshot in Decision Prompt kopieren)
5. Send klicken
6. Prüfen, dass die Antwort strukturiertes JSON ist, das dem erwarteten Format entspricht
7. Prüfen, dass Konfidenzwert, Signalrichtung und Begründungsfelder vorhanden sind
8. Token-Anzahl prüfen, um die täglichen LLM-Kosten zu schätzen

**LLM-Konnektivität nach Konfigurationsänderung prüfen:**

1. LLM Checker öffnen
2. Das geänderte LLM-Modul auswählen
3. Eine einfache Testnachricht eingeben ("Antworte mit 'OK', wenn du mich hören kannst")
4. Send klicken
5. Wenn eine Antwort eintrifft, ist das Modul verbunden

**Tool-Calling-Verhalten prüfen:**

1. LLM Checker öffnen
2. Das LLM-Modul auswählen
3. Einen System-Prompt schreiben, der das LLM anweist, ein bestimmtes Tool zu verwenden
4. Die Tool-Definition im Tools-Panel hinzufügen
5. Senden und prüfen, dass das LLM einen tool_call-Block mit korrekten Parametern zurückgibt

### LLM Checker und Kostenmanagement

Jeder LLM-Aufruf im LLM Checker verbraucht API-Credits. Die Token-Anzeige zeigt die Kosten jedes Tests. Das sollte beim umfangreichen Prompt-Testen berücksichtigt werden:

- Für die initiale Prompt-Erstellung ein günstigeres Modell verwenden (GPT-4o-mini oder Claude Haiku)
- Für die finale Validierung auf das Produktionsmodell wechseln
- Ein typischer M5-Snapshot mit vollständigem Analyse-Prompt verbraucht 800–2000 Input-Tokens

Siehe [LLM Modules](ui.config.llm_modules.de.md) für die Modellkonfiguration.

Vorgesehener Screenshot:
- [LLM Checker](image/ui-24-llm-checker.png)

---

## Tool Executor

`Tool Executor` wird verwendet, um ein bestimmtes Tool direkt aufzurufen und dessen Ausgabe zu prüfen.

Einsatzbereiche:

- sicherstellen, dass ein Tool erreichbar ist und erwartete Daten liefert
- Tool-Parameter testen, bevor sie in ein Snapshot-Profil eingebettet werden
- Tool-Ausgaben debuggen, die in Agentenläufen unerwartet erscheinen
- das Datenformat einer Tool-Ausgabe prüfen, bevor ein Transform-Script geschrieben wird

### Wie Tool Executor funktioniert

Tool Executor ermöglicht:

1. Ein Tool aus der Liste verfügbarer System-Tools auswählen
2. Eingabeparameter als JSON eingeben
3. Das Tool direkt ausführen
4. Die rohe Ausgabe prüfen

Die Ausgabeansicht zeigt:
- die rohe Tool-Antwort (JSON oder Text)
- Ausführungszeit
- etwaige Fehlermeldungen

### Typischer Tool-Executor-Ablauf

**Bevor ein Tool einem Snapshot-Profil hinzugefügt wird:**

1. Tool Executor öffnen
2. Das hinzuzufügende Tool auswählen (z. B. `get_ohlcv`, `get_atr`, `get_swing_levels`)
3. Die geplanten Parameter eingeben (Symbol, Zeitrahmen, Periode usw.)
4. Ausführen
5. Die Ausgabestruktur prüfen
6. Die genauen Schlüsselnamen notieren — das sind die Schlüssel, auf die das Transform-Script über `tool_outputs` zugreift
7. Prüfen, dass die Werte für den aktuellen Markt plausibel sind

**Ein Snapshot-Tool debuggen, das unerwartete Werte zurückgibt:**

1. Tool Executor öffnen
2. Das Tool auswählen, das in Agentenläufen unerwartete Ausgaben liefert
3. Dieselben Parameter eingeben, die im Snapshot-Profil verwendet werden
4. Ausführen
5. Die Ausgabe mit dem vergleichen, was im Agent-Chat-Inspector-Snapshot-Tab erschienen ist
6. Weichen die Ausgaben ab, könnte ein Timing-Problem oder ein Parameter-Mismatch vorliegen

**Konto-Tools vor dem Aktivieren des Live-Handels prüfen:**

1. Tool Executor öffnen
2. `get_account_status` auswählen
3. Ohne Parameter ausführen
4. Prüfen, dass Kontosaldo, Equity und freie Margin korrekt sind
5. `get_open_positions` auswählen
6. Ausführen und prüfen, dass etwaige offene Positionen korrekt gemeldet werden

### Verfügbare Tool-Kategorien

Im Tool Executor verfügbare Tools umfassen:

- **Marktdaten**: OHLCV-Kerzen, ATR, gleitende Durchschnitte, Swing-Levels
- **Kontodaten**: Saldo, Equity, Margin, offene Positionen
- **Orderverwaltung**: ausstehende Orders, Positionsdetails
- **System-Utilities**: aktuelle Uhrzeit, Session-Status, Wirtschaftskalender

Siehe [Tools-Referenz](openforexai.tools.en.md) für vollständige Tool-Dokumentation.

Vorgesehene Screenshots:
- [LLM Checker](image/ui-24-llm-checker.png)
- [Tool Executor](image/ui-25-tool-executor.png)
