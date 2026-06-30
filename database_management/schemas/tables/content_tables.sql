-- ============================================================================
-- PERIDOCS SCHEMAS: CONTENT SCHEMA & RELATED DEPENDENCIES
-- Location: database-management/schemas/tables/content_tables.sql
--save-state: 2026-06-30T13:12-04:00
-- ============================================================================

-- Primary text entry registry (Migrated cleanly from Section 04)
CREATE TABLE IF NOT EXISTS content.entries (
    entry_id                             VARCHAR(64) PRIMARY KEY,
    entry_nickname                       VARCHAR(255),
    timestamp                            TIMESTAMPTZ NOT NULL,
    user_id                              VARCHAR(64), -- we're intentionally allowing anonymous entries
    
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

-- ----------------------------------------------------------------------------
-- 3. STANDALONE CURATED KNOWLEDGE RESOURCES
-- ----------------------------------------------------------------------------
-- Core registry for standalone outlinks to Creative Commons, Public Domain,
-- and open-access materials triggered by inference rules.
CREATE TABLE IF NOT EXISTS content.resources (
    resource_id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title                                VARCHAR(255) NOT NULL,
    resource_url                         TEXT NOT NULL UNIQUE,
    description                          TEXT,               -- Explains the resource scope
    license_type                         VARCHAR(100),       -- e.g., 'CC-BY-SA 4.0', 'Public Domain'
    
    -- Telemetry and Governance
    created_at                           TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at                           TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Optimization index for lightning-fast outlink resolution during inference evaluations
CREATE INDEX IF NOT EXISTS idx_resources_url ON content.resources(resource_url);