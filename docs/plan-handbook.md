# Plan: Persönliches Handbuch (Knowledge Base)

## Ziel

Ein vollständig integriertes, professionelles Dokumentationssystem direkt im System. Der Benutzer kann eigene Erfahrungen, Strategien und Notizen strukturiert erfassen, verwalten und durchsuchen — in einem eigenen Fenster, erreichbar über das Action-Menü.

---

## Kernfunktionen

| Funktion | Beschreibung |
|---|---|
| Dokumente | Erstellen, bearbeiten, löschen, umbenennen |
| Formatierung | Überschriften, Fett/Kursiv, Code, Zitate, Listen |
| Tabellen | Vollständig editierbar mit beliebig vielen Spalten/Zeilen |
| Bilder | Upload + Einbettung direkt im Dokument |
| Interne Links | `[[Dokumentname]]` springt direkt zum verlinkten Dokument |
| Externe Links | Standard HTTP-Links |
| Volltextsuche | Dokumentübergreifend, Treffer mit Kontext-Vorschau |
| Kategorien/Tags | Freie Vergabe, Filterung in der Seitenleiste |
| Inhaltsverzeichnis | Automatisch aus Überschriften generiert |
| Dunkles Design | Passend zum bestehenden UI |

---

## Technologie-Entscheidungen

### Editor
**TipTap** (Open Source, MIT-Lizenz)

Begründung:
- Moderner WYSIWYG-Editor auf ProseMirror-Basis
- React-native, funktioniert direkt mit dem bestehenden Vite/React-Stack
- Fertige Extensions: Tabellen, Bilder, Links, Überschriften, Codeblöcke, Farbgebung
- Unterstützt Custom Extensions (z.B. `[[interne links]]`)
- Export zu HTML und JSON — beide gut persistierbar

Alternativen die ausgeschlossen wurden:
- Monaco Editor (bereits vorhanden): Reiner Code-Editor, kein WYSIWYG
- React Markdown (bereits vorhanden): Nur Anzeige, kein Bearbeiten

### Datenspeicherung
**SQLite** (bereits im System)

Dokumente werden als TipTap-JSON gespeichert. Bilder als base64 im selben Dokument oder als separate Blob-Einträge.

Für Volltextsuche: **SQLite FTS5** — Virtual Table parallel zur Dokumententabelle, automatisch aktualisiert per Trigger.

### Fenstermodell
**`window.open()`** — Eigenes Browser-Fenster mit dedizierter URL.

Das bestehende System verwendet bereits dieses Muster. Das Handbuch-Fenster lädt dieselbe React-App, erkennt anhand des URL-Parameters (`?view=handbook`) dass es als Handbuch-Modus startet, und rendert das Handbuch-Layout.

---

## Architektur

### Datenbankschema (neue Migration: `007_handbook.sql`)

```sql
CREATE TABLE handbook_documents (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL DEFAULT '{}',  -- TipTap JSON
    tags        TEXT NOT NULL DEFAULT '[]',  -- JSON array
    parent_id   TEXT REFERENCES handbook_documents(id),
    sort_order  INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- FTS5 für Volltextsuche
CREATE VIRTUAL TABLE handbook_fts USING fts5(
    title,
    content_text,  -- plain text extrahiert aus TipTap-JSON
    content=handbook_documents,
    tokenize='unicode61'
);

-- Trigger: FTS automatisch aktualisieren
CREATE TRIGGER handbook_fts_insert AFTER INSERT ON handbook_documents BEGIN
    INSERT INTO handbook_fts(rowid, title, content_text)
    VALUES (new.rowid, new.title, new.content);
END;
CREATE TRIGGER handbook_fts_update AFTER UPDATE ON handbook_documents BEGIN
    INSERT INTO handbook_fts(handbook_fts, rowid, title, content_text)
    VALUES ('delete', old.rowid, old.title, old.content);
    INSERT INTO handbook_fts(rowid, title, content_text)
    VALUES (new.rowid, new.title, new.content);
END;
CREATE TRIGGER handbook_fts_delete AFTER DELETE ON handbook_documents BEGIN
    INSERT INTO handbook_fts(handbook_fts, rowid, title, content_text)
    VALUES ('delete', old.rowid, old.title, old.content);
END;
```

### Backend API (neuer Router `/handbook`)

| Method | Endpoint | Beschreibung |
|---|---|---|
| `GET` | `/handbook/documents` | Alle Dokumente (nur Metadaten, kein Content) |
| `POST` | `/handbook/documents` | Neues Dokument erstellen |
| `GET` | `/handbook/documents/{id}` | Einzelnes Dokument mit Content |
| `PUT` | `/handbook/documents/{id}` | Dokument speichern (title + content + tags) |
| `DELETE` | `/handbook/documents/{id}` | Dokument löschen |
| `GET` | `/handbook/search?q={query}` | Volltextsuche, gibt Treffer mit Kontext zurück |
| `POST` | `/handbook/documents/{id}/image` | Bild hochladen, gibt Referenz zurück |

### Frontend-Struktur

```
ui/src/
├── components/views/action/
│   └── Handbook.tsx          ← Button im Action-Menü (öffnet neues Fenster)
├── handbook/                 ← Eigenständige Handbuch-App
│   ├── HandbookApp.tsx       ← Root-Komponente für Handbuch-Modus
│   ├── components/
│   │   ├── DocumentTree.tsx  ← Seitenleiste: Dokumentbaum + Tags
│   │   ├── Editor.tsx        ← TipTap Editor-Komponente
│   │   ├── Toolbar.tsx       ← Formatierungsleiste
│   │   ├── TableOfContents.tsx
│   │   └── SearchPanel.tsx   ← Volltextsuche-Overlay
│   ├── extensions/
│   │   └── InternalLink.ts   ← Custom TipTap Extension für [[Links]]
│   └── api/
│       └── handbook.ts       ← API-Client für alle Handbook-Endpoints
```

---

## UI-Layout (Handbuch-Fenster)

```
┌─────────────────────────────────────────────────────────┐
│ [🔍 Suche...]            [+ Neu]  [⚙ Einstellungen]     │
├──────────────┬──────────────────────────┬───────────────┤
│ DOKUMENTE    │                          │ INHALT        │
│              │   # Titel des Dokuments  │               │
│ ▼ Strategien │                          │ 1. Überschrift│
│   EURUSD     │   Text, Tabellen,        │ 2. Abschnitt  │
│   USDJPY     │   Bilder, Links...       │ 3. Fazit      │
│              │                          │               │
│ ▶ Erfahrungen│   ┌──────────────────┐  │               │
│ ▶ Regeln     │   │ Tabelle          │  │               │
│              │   ├──────┬───────────┤  │               │
│ TAGS         │   │ Col1 │ Col2      │  │               │
│ #eurusd      │   └──────┴───────────┘  │               │
│ #strategie   │                          │               │
│              │   [[anderes-dokument]]   │               │
└──────────────┴──────────────────────────┴───────────────┘
```

---

## Implementierungsschritte

### Phase 1 — Backend & DB (ca. 1 Tag)
1. Migration `007_handbook.sql` anlegen
2. DB-Port: `handbook`-Methoden zu `AbstractRepository` hinzufügen
3. SQLite-Implementierung
4. FastAPI-Router `/handbook` mit allen Endpoints
5. FTS5-Volltextsuche mit Snippet-Extraktion

### Phase 2 — Frontend Grundstruktur (ca. 1 Tag)
1. TipTap installieren (`@tiptap/react`, Core Extensions, Tables, Images)
2. `HandbookApp.tsx` + URL-Parameter-Erkennung in `App.tsx`
3. `Handbook.tsx`-Button im Action-Menü + `window.open()`
4. `DocumentTree.tsx` mit Lade- und Klicklogik
5. Grundlegendes Layout (3-Spalten, dark theme)

### Phase 3 — Editor & Features (ca. 1–2 Tage)
1. TipTap Editor mit allen Extensions (Tabellen, Bilder, Code, Links)
2. Toolbar-Komponente
3. Custom Extension `InternalLink` für `[[Dokumentname]]`
4. Auto-Save (debounced, alle 2 Sekunden nach letzter Änderung)
5. Inhaltsverzeichnis aus Überschriften

### Phase 4 — Suche & Polish (ca. 0,5 Tage)
1. Suchoverlay mit Live-Ergebnissen
2. Treffer-Highlighting
3. Tag-Filter in Seitenleiste
4. Tastaturkürzel (Strg+K für Suche, Strg+S für Speichern)

---

## Abhängigkeiten (neue npm-Pakete)

```json
"@tiptap/react": "^2.x",
"@tiptap/starter-kit": "^2.x",
"@tiptap/extension-table": "^2.x",
"@tiptap/extension-table-row": "^2.x",
"@tiptap/extension-table-cell": "^2.x",
"@tiptap/extension-table-header": "^2.x",
"@tiptap/extension-image": "^2.x",
"@tiptap/extension-link": "^2.x",
"@tiptap/extension-placeholder": "^2.x",
"@tiptap/extension-typography": "^2.x"
```

Keine Backend-Abhängigkeiten — SQLite FTS5 ist in der vorhandenen `aiosqlite`-Installation enthalten.

---

## Offene Entscheidungen

1. **Dokumenthierarchie:** Flache Liste mit Tags, oder echter Ordnerbaum mit `parent_id`? Empfehlung: Ordnerbaum, da `parent_id` bereits im Schema ist.
2. **Bildsspeicherung:** base64 im Dokument (einfach, kein extra Endpoint) vs. separate Tabelle (sauberer, aber komplexer). Empfehlung: base64 für den Start.
3. **Export:** Soll es einen PDF- oder Markdown-Export geben? Technisch mit TipTap einfach nachrüstbar.
