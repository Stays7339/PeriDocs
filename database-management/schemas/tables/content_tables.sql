-- ============================================================================
-- PERIDOCS SCHEMAS: CONTENT SCHEMA & RELATED DEPENDENCIES
-- Location: database-management/schemas/tables/content_tables.sql
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. ADMIN OBJECTS
-- ----------------------------------------------------------------------------
-- Tracks the pinned version bundle required for full pipeline determinism
CREATE TABLE IF NOT EXISTS "ADMIN".release_information (
    release_id VARCHAR(64) PRIMARY KEY,
    schema_version VARCHAR(32) NOT NULL,
    ontology_version VARCHAR(32) NOT NULL, -- Pins the 'KB' state
    rule_set_version VARCHAR(32) NOT NULL, -- Pins the deterministic 'NLP' state
    deployed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT FALSE NOT NULL
);

-- Guarantee that only one system version can be flagged active at any single moment
CREATE UNIQUE INDEX IF NOT EXISTS uidx_active_release 
ON "ADMIN".release_information (is_active) 
WHERE is_active = TRUE;

-- ----------------------------------------------------------------------------
-- 2. IDENTITY PATHWAYS
-- ----------------------------------------------------------------------------
-- Internal developer or curator administrative profiles
CREATE TABLE IF NOT EXISTS "APP".users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL, -- Cryptographically verified via SCRAM/Pgcrypto
    assigned_role VARCHAR(20) NOT NULL CHECK (assigned_role IN ('admin', 'curator', 'auditor')),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    last_login TIMESTAMPTZ
);

-- ----------------------------------------------------------------------------
-- 3. CONTENT OBJECTS
-- ----------------------------------------------------------------------------
-- Stores non-clinical, non-diagnostic mental health resources
CREATE TABLE IF NOT EXISTS "CONTENT".resources (
    resource_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    body_content TEXT NOT NULL,       -- The un-segmented canonical text payload
    source_origin VARCHAR(255),       -- Reference or source attribution
    created_by UUID NOT NULL REFERENCES "APP".users(user_id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Index optimization for audit lookups and attribution joins
CREATE INDEX IF NOT EXISTS idx_resources_creator ON "CONTENT".resources(created_by);

COMMIT;



-- ============================================================
-- 04. ENTRIES TABLE
-- Target File: content_tables.sql
-- Description: Mirrors the exact structured JSON keys for platform input.
-- ============================================================

CREATE TABLE IF NOT EXISTS public.entries (
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

-- Optimization indexes for rehydration, user audit history, and fast queries
CREATE INDEX IF NOT EXISTS idx_entries_user_id ON public.entries(user_id);
CREATE INDEX IF NOT EXISTS idx_entries_timestamp ON public.entries(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_entries_crisis_flag ON public.entries(crisis_flag) WHERE crisis_flag = TRUE;