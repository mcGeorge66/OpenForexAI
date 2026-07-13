[Zurück zu Config](ui.config.de.md)

# Snapshot Config

`Snapshot Config` wird verwendet, um festzulegen, welche Daten gesammelt,
interpretiert und in einen snapshotgestützten Agentenlauf weitergegeben werden.

Aktuelle Hauptfunktionen:

- Snapshot-Profil auswählen
- Execute-Kontext-Agent auswählen
- neues leeres Profil anlegen
- aktuelles Profil aktualisieren
- geänderte Version als neues Profil speichern
- Profil löschen
- toolbasierte Snapshot-Blöcke konfigurieren
- Decision-Payload-Verhalten konfigurieren
- Decision-Semantik konfigurieren
- Execute-Preview ausführen

Diese Seite ist nicht nur ein Schema-Editor. Sie ist auch die praktische
Arbeitsoberfläche für den konkreten Runtime-Snapshot, den ein Agentenzyklus
verwendet.

Vorgesehene Screenshots:
- [Snapshot Config Editor](image/ui-15-snapshot-config-editor.png)
- [Snapshot Execute Preview Dialog](image/ui-16-snapshot-execute-preview.png)

## Referenzdokumente

Für die vollständige Konfigurationsreferenz, Transform-Skripte und
Helferfunktionen:

- [Snapshot-Konfigurationsleitfaden](snapshot-config-guide.de.md)
- [Snapshot-Transformers](snapshot-transformers.de.md)
- [Snapshot-Helferfunktionen](snapshot-helper-functions.de.md)

## Helper Config

Die Seite `Helper Config` ermöglicht die Bearbeitung von
`config/snapshot_helpers.py` — den optionalen Python-Helferfunktionen, die
in Snapshot-Transform-Skripten verfügbar sind.

Der Editor führt beim Speichern einen serverseitigen Python-Syntaxcheck durch.
