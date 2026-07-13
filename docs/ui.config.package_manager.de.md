[Zurück zum UI-Handbuch](ui.de.md) › [Config](ui.config.de.md)

# Package Manager

`Package Manager` ermöglicht den selektiven Export und Import von Konfigurationspaketen. Damit können Teile der Runtime-Konfiguration zwischen Installationen übertragen, gesichert oder in neuen Umgebungen eingespielt werden.

---

## Workflow

Der Package Manager funktioniert in drei Schritten: **Exportieren → Validieren → Importieren**.

---

## Export-Bereich

### Zu exportierende Bereiche

Checkboxen für jeden unterstützten Konfigurationsbereich:

| Checkbox | Inhalt |
|---|---|
| **Include Agents** | Agenten-Konfigurationen |
| **Include Snapshot Profiles** | Snapshot-Profile |
| **Include Decision Prompt Profiles** | Decision-Prompt-Profile |
| **Include Bridge Tools** | Bridge Tool-Definitionen |
| **Include Event Routing** | Event-Routing-Regeln |
| **Include System Config** | Globale `system.json5` (Standard: deaktiviert) |
| **Strict agent dependencies** | Schlägt fehl wenn referenzierte LLM/Broker-Module nicht vorhanden sind |

### Agenten-Auswahl

Liste aller Agenten aus der aktuellen Konfiguration. Jeder Agent hat eine Checkbox. Nur ausgewählte Agenten werden exportiert.

| Schaltfläche | Funktion |
|---|---|
| **Select all** | Alle Agenten auswählen |
| **Clear** | Alle Agenten abwählen |

### Export Selected Areas

Lädt ein `.json5`-Paket mit den ausgewählten Bereichen und einem Zeitstempel im Dateinamen herunter. Deaktiviert wenn keine Bereiche ausgewählt sind.

---

## Paketinhalt-Bereich

Hier wird das zu importierende Paket eingegeben.

| Element | Funktion |
|---|---|
| **Drag & Drop Zone** | `.json5`, `.json` oder `.txt`-Datei hineinziehen |
| **Load package file** | Öffnet Dateiauswahl |
| **Textarea** | Paket-JSON5 direkt einfügen oder bearbeiten |

---

## Mapping & Import-Bereich

### Mapping-Felder

Ermöglichen das Umbenennen von IDs beim Import — notwendig wenn die Ziel-Installation andere Modul- oder Agent-Namen verwendet.

| Feld | Format | Funktion |
|---|---|---|
| **Agent ID Prefix** | Text (z. B. `DEMO-`) | Wird vor alle importierten Agent-IDs gesetzt |
| **Broker Mapping** | Je Zeile: `alt=neu` | Benennt Broker-Modul-Namen um |
| **LLM Mapping** | Je Zeile: `alt=neu` | Benennt LLM-Modul-Namen um |
| **Agent ID Mapping** | Je Zeile: `alt=neu` | Benennt spezifische Agent-IDs um |

**Beispiel Broker Mapping:**
```
broker_oanda=broker_live
broker_demo=broker_paper
```

### Import-Optionen

| Checkbox | Funktion |
|---|---|
| **Replace existing agents** | Überschreibt Agenten mit gleicher ID (Standard: deaktiviert — doppelte IDs schlagen fehl) |
| **Import agents** | Agenten importieren |
| **Import snapshot profiles** | Snapshot-Profile importieren |
| **Import decision prompt profiles** | Decision-Prompt-Profile importieren |
| **Import bridge tools** | Bridge Tools importieren |
| **Import event routing** | Routing-Regeln importieren |
| **Import system config** | `system.json5` importieren (Standard: deaktiviert) |

### Validate

Validiert das Paket ohne es einzuspielen. Zeigt alle Fehler und Warnungen in der Validierungstabelle. Empfohlen vor jedem Import.

### Import

Spielt das Paket mit allen aktiven Mappings und Optionen ein. Deaktiviert wenn kein Paket vorhanden ist.

---

## Validierungstabelle

Erscheint nach Validate oder fehlgeschlagenem Import. Zeigt:

| Spalte | Inhalt |
|---|---|
| **Level** | `error` (blockiert Import) oder `warning` (Import möglich) |
| **Path** | Pfad zum betroffenen Konfigurationselement |
| **Message** | Beschreibung des Problems |

---

## Typischer Ablauf: Export

1. Bereiche auswählen (Checkboxen)
2. Agenten auswählen
3. **Export Selected Areas** klicken → Datei wird heruntergeladen

## Typischer Ablauf: Import

1. Paket-Datei in die Drop-Zone ziehen oder laden
2. Mapping-Felder ausfüllen falls IDs angepasst werden müssen
3. Import-Optionen prüfen
4. **Validate** klicken und Validierungstabelle prüfen
5. Fehler im Paket oder in den Mappings korrigieren
6. **Import** klicken
