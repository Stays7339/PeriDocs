-- ============================================================================
-- PERIDOCS SCHEMAS: KB SCHEMA (ONTOLOGY & KNOWLEDGE BASE LOGIC)
-- Location: database-management/schemas/tables/kb_tables.sql
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. THE RECOGNIZED CONCEPT REGISTRY
-- ----------------------------------------------------------------------------
-- Core registry of the 500-concept ontology vocabulary.
-- This ensures the identification layer never emits a positive label outside
-- of this controlled, pinned vocabulary.
CREATE TABLE IF NOT EXISTS "KB".concepts (
    concept_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    concept_code VARCHAR(100) UNIQUE NOT NULL, -- Machine-readable string (e.g., 'AFF_SADNESS')
    pref_label VARCHAR(150) NOT NULL,          -- Human-readable preferred term
    definition TEXT NOT NULL,                  -- Strict semantic scope note
    concept_scheme VARCHAR(50) NOT NULL CHECK (concept_scheme IN ('QUESTION_SEMANTICS', 'ANSWER_SEMANTICS')),
    
    -- Governance and Evolution Tracking
    introduced_in_release VARCHAR(64) NOT NULL REFERENCES "ADMIN".release_information(release_id),
    is_deprecated BOOLEAN DEFAULT FALSE NOT NULL,
    deprecated_in_release VARCHAR(64) REFERENCES "ADMIN".release_information(release_id),
    
    CONSTRAINT chk_deprecation_release CHECK (
        (is_deprecated = FALSE AND deprecated_in_release IS NULL) OR
        (is_deprecated = TRUE AND deprecated_in_release IS NOT NULL)
    )
);

-- Indexing for rapid validation sweeps by the rule-based extractor
CREATE INDEX IF NOT EXISTS idx_kb_concepts_active_code 
ON "KB".concepts (concept_code) 
WHERE is_deprecated = FALSE;

-- ----------------------------------------------------------------------------
-- 2. HIERARCHICAL RELATIONSHIPS (SKOS / BROADER-NARROWER MAPS)
-- ----------------------------------------------------------------------------
-- Captures taxonomy trees. The retrieval layer leverages these explicit 
-- parent-child paths natively to compute traversal depth weightings.
CREATE TABLE IF NOT EXISTS "KB".concept_hierarchies (
    parent_concept_id UUID NOT NULL REFERENCES "KB".concepts(concept_id) ON DELETE RESTRICT,
    child_concept_id UUID NOT NULL REFERENCES "KB".concepts(concept_id) ON DELETE RESTRICT,
    relationship_type VARCHAR(50) DEFAULT 'broader_than' NOT NULL,
    established_in_release VARCHAR(64) NOT NULL REFERENCES "ADMIN".release_information(release_id),
    
    PRIMARY KEY (parent_concept_id, child_concept_id),
    CONSTRAINT chk_self_reference CHECK (parent_concept_id <> child_concept_id)
);

-- ----------------------------------------------------------------------------
-- 3. INTER-RATER MANAGEMENT & MIGRATION CONTRACTS
-- ----------------------------------------------------------------------------
-- Tracks the inter-rater agreement process. If changes occur or a term 
-- is deprecated, this links affected resources to migration tasks.
CREATE TABLE IF NOT EXISTS "KB".migration_reviews (
    review_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deprecated_concept_id UUID NOT NULL REFERENCES "KB".concepts(concept_id),
    target_resource_id UUID NOT NULL REFERENCES "CONTENT".resources(resource_id) ON DELETE CASCADE,
    assigned_curator_id UUID NOT NULL REFERENCES "APP".users(user_id),
    is_resolved BOOLEAN DEFAULT FALSE NOT NULL,
    resolved_at TIMESTAMPTZ,
    notes TEXT
);

-- ----------------------------------------------------------------------------
-- 4. APPLICATION PRIVILEGES
-- ----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA "KB" TO peri_app;
GRANT SELECT ON ALL TABLES IN SCHEMA "KB" TO peri_app;

GRANT USAGE ON SCHEMA "KB" TO curator;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA "KB" TO curator;

COMMIT;