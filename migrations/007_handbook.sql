-- Migration 007: Personal knowledge base

CREATE TABLE IF NOT EXISTS kb_documents (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT 'Untitled',
    content     TEXT NOT NULL DEFAULT '',
    is_folder   INTEGER NOT NULL DEFAULT 0,
    parent_id   TEXT REFERENCES kb_documents(id) ON DELETE SET NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    tags        TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_kb_parent  ON kb_documents(parent_id);
CREATE INDEX IF NOT EXISTS idx_kb_updated ON kb_documents(updated_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(
    doc_id     UNINDEXED,
    title,
    content,
    tokenize='unicode61 remove_diacritics 1'
);
