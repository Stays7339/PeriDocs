-- ============================================================================
-- PERIDOCS SCHEMAS: KB SCHEMA (ONTOLOGY & KNOWLEDGE BASE LOGIC)
-- Location: database-management/schemas/tables/kb_schema.sql
-- save-state: 2026-07-12T10:50-04:00
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 0. FOUNDATIONAL ADMINISTRATIVE DEPENDENCIES
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS admin.release_information (
    release_id                           VARCHAR(64) PRIMARY KEY,
    release_version                      VARCHAR(50),
    build_target                         VARCHAR(100),
    created_at                           TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 1. THE RECOGNIZED CONCEPT REGISTRY
-- ----------------------------------------------------------------------------
-- Simple flat table replacing the text-file scanning loop for heuristic concepts
CREATE TABLE IF NOT EXISTS kb.concepts (
    concept_id                           VARCHAR(255) PRIMARY KEY, -- e.g., 'concept_from_heuristic:cfh_...'
    label                                TEXT NOT NULL,
    description                          TEXT
);

-- ----------------------------------------------------------------------------
-- 2b. MODERATOR HEURISTICS & OUTLINK RULES
-- ----------------------------------------------------------------------------

-- Holds the moderator-curated evaluation heuristics
CREATE TABLE IF NOT EXISTS kb.heuristics (
    heuristic_id          VARCHAR(12) PRIMARY KEY,
    givens                TEXT[] NOT NULL, -- Array of concept codes or IDs
    outputs               JSONB NOT NULL,  -- List of matching concept weights & reasons
    introduced_in_release VARCHAR(64) NOT NULL REFERENCES admin.release_information(release_id)
);

-- The rule table connecting your external content resources to the concept registry
CREATE TABLE IF NOT EXISTS kb.resource_concept_mappings (
    resource_id UUID REFERENCES content.resources(resource_id) ON DELETE CASCADE,
    concept_id  VARCHAR(255) REFERENCES kb.concepts(concept_id) ON DELETE CASCADE,
    PRIMARY KEY (resource_id, concept_id)
);

-- ----------------------------------------------------------------------------
-- 4. APPLICATION PRIVILEGES
-- ----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA kb TO peri_app; 
GRANT SELECT ON ALL TABLES IN SCHEMA kb TO peri_app; 

GRANT USAGE ON SCHEMA kb TO curator; 
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA kb TO curator; 

COMMIT;