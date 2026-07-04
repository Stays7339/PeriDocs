-- ============================================================================
-- PERIDOCS SCHEMAS: CONTENT SCHEMA & RELATED DEPENDENCIES
-- Location: database-management/schemas/tables/content_schema.sql
-- save-state: 2026-07-03T21:01-04:00
-- ============================================================================

-- 1. Primary Source of Truth Text Entries
CREATE TABLE IF NOT EXISTS content.entries (
    entry_id                             VARCHAR(64) PRIMARY KEY,
    entry_nickname                       VARCHAR(255),
    timestamp                            TIMESTAMPTZ NOT NULL,
    user_id                              VARCHAR(64), 
    safe_text                            TEXT,
    centroids                            JSONB DEFAULT '[]'::jsonb,
    ip_hash                              VARCHAR(128),
    encrypted_raw_ip                     TEXT,
    encrypted_raw_text                   TEXT,
    crisis_flag                          BOOLEAN DEFAULT FALSE,
    hash_from_token_for_deleting_entries TEXT,
    created_at                           TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at                           TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2. Consolidated Master Entry Vectors 
-- (Note: Ensure your Python storage engine targets 'embedding' and 'created_at'!)
CREATE TABLE IF NOT EXISTS content.embeddings (
    entry_id   VARCHAR(64) PRIMARY KEY REFERENCES content.entries(entry_id) ON DELETE CASCADE,
    embedding  REAL[] NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 3. Sliced Text Chunks & Chunk Vectors (Successfully Migrated)
CREATE TABLE IF NOT EXISTS content.entry_windows (
    entry_id         VARCHAR(64) REFERENCES content.entries(entry_id) ON DELETE CASCADE,
    window_index     INT NOT NULL, 
    window_embedding REAL[] NOT NULL, 
    window_text      TEXT NOT NULL,      
    standout_flag    BOOLEAN NOT NULL,   
    PRIMARY KEY (entry_id, window_index)
);

-- 4. Standalone Curated Knowledge Resources (Outlinks)
CREATE TABLE IF NOT EXISTS content.resources (
    resource_id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title                                VARCHAR(255) NOT NULL,
    resource_url                         TEXT NOT NULL UNIQUE,
    description                          TEXT,               
    license_type                         VARCHAR(100),       
    created_at                           TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at                           TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- OPTIMIZATION INDEXES
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_entries_user_id ON content.entries(user_id);
CREATE INDEX IF NOT EXISTS idx_entries_timestamp ON content.entries(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_entries_crisis_flag ON content.entries(crisis_flag) WHERE crisis_flag = TRUE;
CREATE INDEX IF NOT EXISTS idx_resources_url ON content.resources(resource_url);

-- Brought over and corrected from nlp_tables.sql for fast sequence rehydration loops
CREATE INDEX IF NOT EXISTS idx_entry_windows_lookup ON content.entry_windows(entry_id, window_index ASC);