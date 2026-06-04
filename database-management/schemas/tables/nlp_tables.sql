-- ============================================================================
-- PERIDOCS SCHEMAS: NLP, INFERENCE, SEARCH, & AUDIT TABLES
-- Location: database-management/schemas/tables/nlp_tables.sql
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. INFERENCE SCHEMA: EXECUTION CONTEXTS
-- ----------------------------------------------------------------------------
-- Captures the entry vector of every raw user query. 
-- Raw text is isolated and encrypted separately for security and compliance[cite: 22, 88].
CREATE TABLE IF NOT EXISTS "INFERENCE".queries (
    query_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    release_id VARCHAR(64) NOT NULL REFERENCES "ADMIN".release_information(release_id),
    
    -- Text Isolation Partitioning
    encrypted_raw_text TEXT NOT NULL, -- Encrypted for compliance/misuse monitoring only [cite: 22, 90]
    safe_text TEXT,                   -- Anonymized, preprocessed clean input [cite: 23, 24]
    
    -- Processing Metadata Engine
    preprocessing_log JSONB NOT NULL, -- Records spelling/punctuation normalizations [cite: 24, 25, 50]
    is_safe BOOLEAN DEFAULT TRUE NOT NULL,
    received_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Indexing for pipeline compliance audits and text safety tracking
CREATE INDEX IF NOT EXISTS idx_queries_release ON "INFERENCE".queries(release_id);
CREATE INDEX IF NOT EXISTS idx_queries_safety ON "INFERENCE".queries(is_safe) WHERE is_safe = FALSE;

-- ----------------------------------------------------------------------------
-- 2. NLP SCHEMA: PIPELINE TRANSPARENCY & STRUCTURAL CONTRACTS
-- ----------------------------------------------------------------------------
-- Stores the deterministic, versioned output of the rule-based extractor[cite: 34, 48, 50].
-- Enforced via Python-side JSON Schema validation contracts before writing[cite: 93].
CREATE TABLE IF NOT EXISTS "NLP".pipeline_logs (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id UUID NOT NULL UNIQUE REFERENCES "INFERENCE".queries(query_id) ON DELETE CASCADE,
    
    -- The Glass-Box Core Data Payloads
    ontology_tags VARCHAR(100)[] NOT NULL, -- Array of concept_codes emitted by rules [cite: 35, 50]
    uncertainty_diagnostics JSONB NOT NULL, -- Captures polysemy, margins, and conflicts [cite: 35, 46, 50]
    pipeline_provenance JSONB NOT NULL,     -- Explicitly binds script and rule set versions [cite: 47, 50]
    
    -- Governance Routing Signals [cite: 73, 75]
    has_low_candidate_margin BOOLEAN DEFAULT FALSE NOT NULL,
    has_high_retrieval_dispersion BOOLEAN DEFAULT FALSE NOT NULL,
    is_out_of_coverage BOOLEAN DEFAULT FALSE NOT NULL -- Flagged if rule set cannot resolve input [cite: 37, 75]
);

-- GIN (Generalized Inverted Index) for high-speed metadata querying across JSONB blocks
CREATE INDEX IF NOT EXISTS gin_idx_nlp_uncertainty ON "NLP".pipeline_logs USING GIN (uncertainty_diagnostics);
CREATE INDEX IF NOT EXISTS gin_idx_nlp_provenance ON "NLP".pipeline_logs USING GIN (pipeline_provenance);
CREATE INDEX IF NOT EXISTS idx_nlp_tags ON "NLP".pipeline_logs USING GIN (ontology_tags);

-- ----------------------------------------------------------------------------
-- 3. SEARCH SCHEMA: RETRIEVAL & NATIVE MATCHING OUTPUTS
-- ----------------------------------------------------------------------------
-- Tracks the runtime behavior and outcome of the native similarity scoring functions[cite: 65, 66, 88].
CREATE TABLE IF NOT EXISTS "SEARCH".retrieval_logs (
    search_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id UUID NOT NULL REFERENCES "INFERENCE".queries(query_id) ON DELETE CASCADE,
    matched_resource_id UUID REFERENCES "CONTENT".resources(resource_id) ON DELETE SET NULL,
    
    -- Scoring Metrics and Evaluation Baselines [cite: 67, 68]
    computed_similarity_score NUMERIC(5,4) NOT NULL,
    tie_broken_applied BOOLEAN DEFAULT FALSE NOT NULL,
    is_below_minimum_threshold BOOLEAN DEFAULT FALSE NOT NULL, -- Flags null-state matches [cite: 68]
    executed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Indexing to track evaluation metrics and low-scoring search quality clusters
CREATE INDEX IF NOT EXISTS idx_search_query ON "SEARCH".retrieval_logs(query_id);
CREATE INDEX IF NOT EXISTS idx_search_score ON "SEARCH".retrieval_logs(computed_similarity_score);

-- ----------------------------------------------------------------------------
-- 4. AUDIT SCHEMA: IMMUTABLE DATA LEDGER
-- ----------------------------------------------------------------------------
-- The unified transactional memory for the governance loop review queue[cite: 78, 88].
-- Explicitly replaces volatile, file-based persistence layers.
CREATE TABLE IF NOT EXISTS "AUDIT".governance_evidence_packets (
    packet_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id UUID NOT NULL REFERENCES "INFERENCE".queries(query_id),
    log_id UUID NOT NULL REFERENCES "NLP".pipeline_logs(log_id),
    
    -- Curation Routing Contexts [cite: 77, 80]
    routing_reason VARCHAR(50) NOT NULL, -- e.g., 'OUT_OF_COVERAGE', 'LOW_MARGIN', 'RANDOM_SAMPLE' [cite: 75, 77]
    review_status VARCHAR(30) DEFAULT 'PENDING_REVIEW' NOT NULL CHECK (review_status IN ('PENDING_REVIEW', 'UNDER_REVIEW', 'RESOLVED_NO_CHANGE', 'RESOLVED_ONTOLOGY_MUTATION')),
    assigned_reviewer_id UUID REFERENCES "APP".users(user_id) ON DELETE SET NULL,
    
    -- Audit History Tracking
    action_taken_summary TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    resolved_at TIMESTAMPTZ
);

-- Indexing for the curator dashboard workflow queues [cite: 80]
CREATE INDEX IF NOT EXISTS idx_audit_packet_status ON "AUDIT".governance_evidence_packets(review_status);

-- ----------------------------------------------------------------------------
-- 5. RUNTIME ROLE PERMISSIONS
-- ----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA "INFERENCE", "NLP", "SEARCH", "AUDIT" TO peri_app;

-- The app engine needs to write logs, metrics, and trigger review packets natively 
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA "INFERENCE" TO peri_app;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA "NLP" TO peri_app;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA "SEARCH" TO peri_app;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA "AUDIT" TO peri_app;

-- Curators and auditors need access to drive the governance packet review cycle [cite: 80]
GRANT USAGE ON SCHEMA "AUDIT" TO curator, auditor;
GRANT SELECT, UPDATE ON TABLE "AUDIT".governance_evidence_packets TO curator;
GRANT SELECT ON ALL TABLES IN SCHEMA "AUDIT" TO auditor;

COMMIT;
