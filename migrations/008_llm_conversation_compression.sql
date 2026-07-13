-- Migration 008: Add is_compressed flag to agent_conversations
-- Allows zlib-compressed storage of LLM message histories.
-- is_compressed = 0  → messages column is plain JSON (legacy / uncompressed)
-- is_compressed = 1  → messages column is zlib-compressed bytes stored as BLOB

ALTER TABLE agent_conversations ADD COLUMN is_compressed INTEGER NOT NULL DEFAULT 0;
