[Zurück zu Config](ui.config.de.md)

# System Config

System Config ist ein direkter Editor für die zentrale Konfigurationsdatei `config/system.json5`. Diese Datei steuert das globale Laufzeitverhalten des gesamten Systems — Log-Level, Broker-Zeitzonen-Offset, Management-API-Einstellungen, LLM-Modul-Referenzen, Broker-Modul-Referenzen, Snapshot-Profile, Decision-Prompt-Profile, Agenten und Event-Composer.

> **Achtung:** Dies ist die einflussreichste Konfigurationsseite. Fehler in der `system.json5` können das System am Start hindern oder gleichzeitig falsches Verhalten bei allen Agenten verursachen. Die spezialisierten Wizard-Seiten (Agent Config, Entity Config) für agentenspezifische Änderungen verwenden und System Config für globale Einstellungen reservieren, die keine dedizierte UI haben.

---

## Inhaltsverzeichnis

1. [Oberfläche](#oberfläche)
2. [Speicherverhalten und Validierung](#speicherverhalten-und-validierung)
3. [JSON5-Syntax-Grundlagen](#json5-syntax-grundlagen)
4. [Wichtige Abschnitte der system.json5](#wichtige-abschnitte-der-systemjson5)
5. [Der `system`-Abschnitt](#der-system-abschnitt)
6. [broker_candle_utc_offset_hours — Kritische Einstellung](#broker_candle_utc_offset_hours--kritische-einstellung)
7. [Der `modules`-Abschnitt](#der-modules-abschnitt)
8. [Der `snapshot_profiles`-Abschnitt](#der-snapshot_profiles-abschnitt)
9. [Der `decision_prompt_profiles`-Abschnitt](#der-decision_prompt_profiles-abschnitt)
10. [Der `agents`-Abschnitt](#der-agents-abschnitt)
11. [Der `event_composers`-Abschnitt](#der-event_composers-abschnitt)
12. [Typischer Ablauf](#typischer-ablauf)
13. [Wann System Config vs. dedizierte Seiten verwenden](#wann-system-config-vs-dedizierte-seiten-verwenden)
14. [Wiederherstellung nach einer defekten system.json5](#wiederherstellung-nach-einer-defekten-systemjson5)

---

## Oberfläche

Der System Config-Bildschirm besteht aus vier Elementen:

### Kopfleiste

| Element | Funktion |
|---------|----------|
| **Dateipfad** | Zeigt den vollständigen Pfad zu `config/system.json5` |
| **Refresh** | Lädt die aktuelle Datei von der Festplatte neu und verwirft ungespeicherte Bearbeitungen |
| **Save** | Validiert den JSON5-Inhalt und schreibt ihn auf die Festplatte |
| **Position** | Zeigt die aktuelle Cursor-Position als Zeile:Spalte |

### Zeilennummern

Links im Editor angezeigt, synchron mit dem Text scrollend. Position-Anzeige in der Kopfleiste zur Navigation zu einer bestimmten Zeile verwenden.

### Editor-Textarea

Freitextbearbeitungsbereich für `system.json5`. Syntax-Hervorhebung (nur visuelles Hilfsmittel — die Textarea bleibt vollständig bearbeitbar):

| Farbe | Angewendet auf |
|-------|---------------|
| Cyan | Objekt-Keys |
| Grün | String-Werte |
| Amber | Boolean-Werte (`true`, `false`) |
| Grau | `null`-Werte |
| Lila | Numerische Werte |

JSON5-Kommentare (`//` und `/* */`) werden in einem gedämpften Ton angezeigt und beim Speichern beibehalten.

### Status-Meldungen

- **„Saved."** — Datei wurde erfolgreich geschrieben
- **Fehlermeldung** — Inline angezeigt wenn Validierung fehlschlägt; Datei wird nicht geschrieben

---

## Speicherverhalten und Validierung

Beim Klicken auf Save:

1. Parst der Editor-Inhalt als JSON5 (unterstützt Kommentare, abschließende Kommas, Keys ohne Anführungszeichen)
2. Prüft ob das Ergebnis der obersten Ebene ein JSON-Objekt ist (kein Array, kein primitiver Wert)
3. Bei Parse-Fehler: Fehlermeldung mit Zeile/Spalte des Syntaxfehlers; Datei wird nicht geschrieben
4. Bei Erfolg: Datei auf Festplatte geschrieben, „Saved." angezeigt

**Wichtig**: Ein laufendes System liest `system.json5` nicht automatisch neu. Änderungen treten beim nächsten Systemstart oder beim Neuladen des betroffenen Moduls in Kraft. Wenn nur ein Modul-Referenzpfad geändert wird, System neu starten. Für Agenten-Konfigurationsänderungen bietet die dedizierte Agent Config-Seite Hot-Reload ohne vollständigen Neustart.

---

## JSON5-Syntax-Grundlagen

`system.json5` verwendet das JSON5-Format, eine Obermenge von JSON mit Komfortverbesserungen:

```json5
{
  // Einzeilige Kommentare erlaubt
  /* Block-Kommentare auch */
  
  system: {
    log_level: "INFO",            // Keys ohne Anführungszeichen gültig
    broker_candle_utc_offset_hours: 3,
    trailing_comma_ok: true,      // Abschließende Kommas bei letzten Einträgen erlaubt
  },
  
  modules: {
    llm: ["config/llm/azure_azmin.json5"],
    broker: ["config/broker/oxs_mt5.json5"],
  }
}
```

Keys benötigen keine Anführungszeichen, außer sie enthalten Sonderzeichen. Abschließende Kommas beim letzten Element sind erlaubt. Ein- und mehrzeilige Kommentare bleiben erhalten.

---

## Wichtige Abschnitte der system.json5

| Abschnitt | Zweck |
|-----------|-------|
| `system` | Globale Laufzeitparameter (Log-Level, Zeitzonen-Offset, API-Einstellungen) |
| `modules` | Dateipfade zu LLM- und Broker-Modul-Konfigurationsdateien |
| `snapshot_profiles` | Snapshot-Profil-Definitionen (oder Pfade zu Profildateien) |
| `decision_prompt_profiles` | Decision-Prompt-Profil-Definitionen |
| `agents` | Alle Agenten-Definitionen |
| `event_composers` | Alle EC-Entitäts-Definitionen |

---

## Der `system`-Abschnitt

```json5
{
  system: {
    log_level: "INFO",
    broker_candle_utc_offset_hours: 3,
    management_api: {
      host: "0.0.0.0",
      port: 8765,
    },
    ui: {
      dev_server: {
        enabled: false,
        port: 5173,
      }
    }
  }
}
```

### `log_level`

Steuert die Ausführlichkeit des System-Loggings.

| Wert | Verhalten |
|------|-----------|
| `DEBUG` | Alle Meldungen einschließlich Bus-Zustelltraces, Template-Auflösungen, Tool-Timings |
| `INFO` | Normale Betriebsmeldungen: Agenten-Zyklen, Entscheidungen, Order-Platzierungen |
| `WARNING` | Nur Probleme, die Aufmerksamkeit erfordern könnten, den Betrieb aber nicht stoppen |
| `ERROR` | Nur Fehler, die das Abschließen einer Aktion verhindert haben |

`DEBUG` bei der Untersuchung von Routing- oder Snapshot-Problemen verwenden. Für den normalen Betrieb zu `INFO` zurückwechseln — DEBUG erzeugt sehr hohes Log-Volumen.

### `management_api`

Der HTTP-API-Server, der von der UI verwendet wird.

| Feld | Standard | Beschreibung |
|------|----------|--------------|
| `host` | `"0.0.0.0"` | Bind-Adresse. `"127.0.0.1"` verwenden um auf Localhost zu beschränken. |
| `port` | `8765` | Port-Nummer. Ändern wenn Port belegt ist. |

### `ui.dev_server`

Nur für Entwicklung. Wenn `enabled: true`, stellt das Backend die UI auf dem Dev-Server-Port bereit.

| Feld | Standard | Beschreibung |
|------|----------|--------------|
| `enabled` | `false` | Dev-Server-Modus aktivieren |
| `port` | `5173` | Vite Dev-Server-Port |

Im Produktionsbetrieb `enabled: false` lassen.

---

## broker_candle_utc_offset_hours — Kritische Einstellung

Dieser einzelne Wert hat einen großen Einfluss auf die Genauigkeit der Handelssession. Diesen Abschnitt vor einer Änderung sorgfältig lesen.

### Was es ist

`broker_candle_utc_offset_hours` ist der UTC-Offset der Broker-Serverzeit. Beispiele:
- Ein Broker auf UTC+3 (häufig bei MT5-Brokern, die EEST folgen): `3`
- Ein Broker auf UTC+0: `0`
- Ein Broker auf UTC+2 (EET-Standard): `2`

### Warum es wichtig ist

Kerzen-Zeitstempel, die von MT5 zurückgegeben werden, sind in der Broker-Server-Lokalzeit — nicht UTC. Die Kerze für `2024-03-15 12:00:00` bei einem UTC+3-Broker repräsentiert tatsächlich `2024-03-15 09:00:00 UTC`.

Der Session-Filter im System muss diesen Broker-lokalen Kerzen-Zeitstempel mit konfigurierten Session-Grenzen vergleichen (z.B. London Open um 08:00 UTC, New York Close um 21:00 UTC). So funktioniert der Vergleich:

1. Das System konvertiert Session-Grenzen von UTC in Broker-Lokalzeit mit `broker_candle_utc_offset_hours`
2. Die konvertierte Grenze wird mit dem Kerzen-Zeitstempel verglichen

### Session-Grenzen-Konvertierungsbeispiel

**Szenario**: Die Session soll 30 Minuten vor New York Close enden.

- New York schließt um 17:00 EDT = 21:00 UTC
- Broker ist UTC+3: 21:00 UTC → 00:00 Broker-Zeit (Mitternacht)
- Post-Session-Puffer: -30 Min → Session endet um 23:30 Broker-Zeit
- Das System berechnet: `session_end_broker_time = 23:30`
- Eine Kerze mit Zeitstempel `23:15` (Broker) liegt in der Session
- Eine Kerze mit Zeitstempel `23:45` (Broker) liegt außerhalb der Session → Trigger übersprungen

### Wenn der Wert falsch ist

Wenn `broker_candle_utc_offset_hours` nicht mit dem tatsächlichen Server-UTC-Offset des Brokers übereinstimmt:

- Session-Filter löst zu falschen Zeiten aus (um den UTC-Offset-Fehler verschoben)
- Beispiel: Broker ist UTC+3 aber du setzt `2` → Session-Grenzen sind 1 Stunde falsch
- Dies kann zu verpassten Signalen in gültigen Handelsstunden oder zu Signalen in verbotenen Stunden führen

### Wie man den UTC-Offset des Brokers findet

1. MT5 öffnen
2. Serverzeit oben rechts notieren
3. Mit der eigenen Ortszeit vergleichen und Offset zu UTC berechnen
4. Häufige Werte: OXS_T verwendet UTC+3 (EEST/EET je nach Sommerzeit)

### DST-Hinweis

MT5-Broker passen ihren Server-UTC-Offset typischerweise zweimal jährlich für die Sommerzeit an:
- Sommer (Ende März bis Ende Oktober): UTC+3 (EEST)
- Winter (Ende Oktober bis Ende März): UTC+2 (EET)

Wenn der Broker diesem Muster folgt, `broker_candle_utc_offset_hours` bei jeder Sommerzeitumstellung aktualisieren. Kalender-Erinnerung einrichten.

---

## Der `modules`-Abschnitt

```json5
{
  modules: {
    llm: [
      "config/llm/azure_azmin.json5"
    ],
    broker: [
      "config/broker/oxs_mt5.json5"
    ]
  }
}
```

Jeder Eintrag ist ein Dateipfad relativ zum Projektstamm. Die referenzierte Datei enthält die vollständige Konfiguration für dieses Modul. Für Details zum Inhalt dieser Dateien siehe [LLM Modules](ui.config.llm_modules.de.md) und [Broker Modules](ui.config.broker_modules.de.md).

Neues LLM oder Broker-Adapter hinzufügen: Konfigurationsdatei-Pfad zum entsprechenden Array hinzufügen und System neu starten.

---

## Der `snapshot_profiles`-Abschnitt

Snapshot-Profile können direkt in `system.json5` definiert oder per Pfad referenziert werden. In den meisten Installationen werden Profile direkt in `system.json5` für Einfachheit einer einzelnen Datei gespeichert. Die Snapshot Config UI-Seite liest aus diesen Definitionen und schreibt in sie.

Die Profilstruktur ist vollständig in [Snapshot Config](ui.config.snapshot_config.de.md) dokumentiert.

---

## Der `decision_prompt_profiles`-Abschnitt

Ähnlich wie Snapshot-Profile. Jedes Profil enthält einen System-Prompt für das LLM und eine User-Message-Vorlage. Die Decision Prompt Config-Seite verwaltet diese. Direkte Bearbeitung in System Config ist möglich, aber die dedizierte Seite ist sicherer.

---

## Der `agents`-Abschnitt

Enthält alle Agenten-Definitionen. Jeder Agent hat:
- `id`: den vollständigen Agent-ID-String
- `type`: Agenten-Implementierungsklasse
- `enabled`: ob dieser Agent gestartet werden soll
- `snapshot_profile`: welches Snapshot-Profil zu verwenden
- `decision_prompt_profile`: welches Prompt-Profil zu verwenden
- `llm`: welches LLM-Modul zu verwenden

Für Änderungen an einzelnen Agenten wird die Agent Config-Seite gegenüber direkter Bearbeitung dieses Abschnitts stark bevorzugt — sie bietet Validierung, Hot-Reload und verhindert versehentliche Beschädigung anderer Agenten.

---

## Der `event_composers`-Abschnitt

Enthält alle EC-Entitäts-Definitionen. Jede EC-Entität hat Gate-Schwellenwerte, Positionsgröße-Parameter und Risikoregeln. Für Änderungen an einzelnen EC-Entitäten wird die Entity Config-Seite stark bevorzugt.

---

## Typischer Ablauf

Für globale Systemeinstellungen (Log-Level, Zeitzonen-Offset, API-Port):

1. **Refresh** klicken um die aktuelle Version zu laden
2. Den `system`-Abschnitt oben in der Datei lokalisieren
3. Zielfeld bearbeiten
4. **Save** klicken
5. Fehlermeldungen prüfen
6. System neu starten wenn erforderlich (die meisten globalen Einstellungen erfordern Neustart)

Für Modul-Pfad-Änderungen:

1. Neue Modul-Konfigurationsdatei erstellen (z.B. `config/llm/neues_llm.json5`)
2. System Config öffnen
3. Dateipfad zu `modules.llm` oder `modules.broker` hinzufügen
4. Speichern
5. Neu starten

---

## Wann System Config vs. dedizierte Seiten verwenden

| Aufgabe | Empfohlenes Werkzeug |
|---------|---------------------|
| Log-Level ändern | System Config |
| Broker-Server-UTC-Offset ändern | System Config |
| Management-API-Port ändern | System Config |
| Neues LLM-Modul hinzufügen | System Config (Pfad hinzufügen) + LLM Modules (Inhalt bearbeiten) |
| Neues Broker-Modul hinzufügen | System Config (Pfad hinzufügen) + Broker Modules (Inhalt bearbeiten) |
| Agenten-Snapshot-Profil bearbeiten | Agent Config |
| Agenten-Prompt bearbeiten | Decision Prompt Config |
| Routing-Regel hinzufügen/ändern | Event Routing |
| EC-Gate-Schwellenwerte bearbeiten | Entity Config |
| Snapshot Tool/Calculation Blocks bearbeiten | Snapshot Config |

---

## Wiederherstellung nach einer defekten system.json5

Wenn eine `system.json5` mit einem Syntaxfehler gespeichert wurde und das System nicht startet:

**Option 1 — Über UI reparieren** (wenn die UI noch lädt)
1. System Config öffnen
2. Editor zeigt den defekten Inhalt
3. Syntaxfehler reparieren (Fehlermeldung auf Zeile/Spalte prüfen)
4. Erneut speichern

**Option 2 — Über Datei-Editor reparieren**
1. `config/system.json5` in einem Texteditor öffnen
2. Syntaxfehler finden und reparieren
3. System neu starten

**Option 3 — Aus Backup wiederherstellen**
Das System schreibt vor jedem Speichern ein Backup nach `config/system.json5.bak`. Wenn die aktuelle Datei beschädigt ist:
1. `config/system.json5` umbenennen in `config/system.json5.broken`
2. `config/system.json5.bak` umbenennen in `config/system.json5`
3. Neu starten

**Häufige Syntaxfehler:**
- Fehlende schließende `}` oder `]`
- Nicht übereinstimmende String-Anführungszeichen
- Ungültige Escape-Sequenzen in Strings
- Ungültiger Bezeichner als Key (Sonderzeichen)

---

*Dieses Dokument behandelt System Config in OpenForexAI v0.7+. Für Konfiguration auf Agenten-Ebene siehe [Agent Config](ui.config.agent_config.de.md). Für LLM-Adapter-Einstellungen siehe [LLM Modules](ui.config.llm_modules.de.md). Für Broker-Adapter-Einstellungen siehe [Broker Modules](ui.config.broker_modules.de.md).*
