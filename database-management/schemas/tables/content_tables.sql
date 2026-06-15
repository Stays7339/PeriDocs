-- ============================================================================
-- PERIDOCS SCHEMAS: CONTENT SCHEMA & RELATED DEPENDENCIES
-- Location: database-management/schemas/tables/content_tables.sql
-- ============================================================================

-- Primary text entry registry (Migrated cleanly from Section 04)
CREATE TABLE IF NOT EXISTS content.entries (
    entry_id                             VARCHAR(64) PRIMARY KEY,
    entry_nickname                       VARCHAR(255),
    timestamp                            TIMESTAMPTZ NOT NULL,
    user_id                              VARCHAR(64) NOT NULL,
    
    -- The core readable and processed content
    safe_text                            TEXT,
    
    -- Backward-compatible array snapshot of original centroid associations
    centroids                            JSONB DEFAULT '[]'::jsonb,
    
    -- Security & Forensic boundaries
    ip_hash                              VARCHAR(128),
    encrypted_raw_ip                     TEXT,
    encrypted_raw_text                   TEXT,
    
    -- Platform telemetry & deletion token checks
    crisis_flag                          BOOLEAN DEFAULT FALSE,
    hash_from_token_for_deleting_entries TEXT,
    
    -- Database lifecycle tracking
    created_at                           TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at                           TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Flat vector array engine table (Relational storage for 1024-dimension float arrays)
CREATE TABLE IF NOT EXISTS content.embeddings (
    entry_id   VARCHAR(64) PRIMARY KEY REFERENCES content.entries(entry_id) ON DELETE CASCADE,
    embedding  REAL[] NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Optimization indexes for high-speed lookup and pipeline execution
CREATE INDEX IF NOT EXISTS idx_entries_user_id ON content.entries(user_id);
CREATE INDEX IF NOT EXISTS idx_entries_timestamp ON content.entries(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_entries_crisis_flag ON content.entries(crisis_flag) WHERE crisis_flag = TRUE;