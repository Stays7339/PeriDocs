-- ====================================================================
-- PeriDocs RADICLE v0 - Access Control Matrix & Permissions
-- Created: 2026-05-16T13:40:00-04:00 by MB
-- Updated: 2026-05-16T14:30:00-04:00 by MB
-- ====================================================================

-- Step 1: Wipe default public inheritance parameters on schemas to harden the cluster
REVOKE ALL ON SCHEMA public FROM PUBLIC;

-- Step 2: Establish the Structural Engineer (migrator) Rights
-- The migrator needs complete power to adjust, append, and patch structures across all domains
GRANT USAGE, CREATE ON SCHEMA CONTENT, KB, SEARCH, INFERENCE, NLP, AUDIT, ADMIN, APP TO migrator;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA CONTENT, KB, SEARCH, INFERENCE, NLP, AUDIT, ADMIN, APP TO migrator;

-- Step 3: Establish Content Steward (curator) Limitations
-- Curators manage resources and ontologies but cannot modify infrastructure or wipe history
GRANT USAGE ON SCHEMA CONTENT, KB, SEARCH, NLP, AUDIT TO curator;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA CONTENT, KB TO curator;
GRANT SELECT ON ALL TABLES IN SCHEMA SEARCH, NLP, AUDIT TO curator;

-- Step 4: Establish Independent Reviewer (auditor) Rights
-- Auditors possess complete passive transparency into pipeline tracking but can never alter history
GRANT USAGE ON SCHEMA AUDIT, ADMIN, NLP, CONTENT, KB TO auditor;
GRANT SELECT ON ALL TABLES IN SCHEMA AUDIT, ADMIN, NLP, CONTENT, KB TO auditor;

-- Step 5: Establish System Governor (admin) Rights
-- High-level operational configuration capabilities, emergency parameter access
GRANT USAGE, CREATE ON SCHEMA ADMIN TO admin;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA ADMIN TO admin;
GRANT USAGE ON SCHEMA AUDIT, NLP, CONTENT, KB, APP TO admin;
GRANT SELECT ON ALL TABLES IN SCHEMA AUDIT, NLP, CONTENT, KB, APP TO admin;

-- Step 6: Secure the FastAPI Application Runtime (peri_app)
-- Restrict to the absolute least privileges required to navigate queries and fulfill sessions
GRANT USAGE ON SCHEMA APP, INFERENCE, CONTENT, KB, SEARCH, NLP TO peri_app;

-- Full read/write management of application states and ephemeral runtime tracking
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA APP, INFERENCE TO peri_app;

-- Purely read-only access to source libraries, vector searches, and diagnostic logging
GRANT SELECT ON ALL TABLES IN SCHEMA CONTENT, KB, SEARCH, NLP TO peri_app;

-- Explicitly ensure that peri_app cannot see or bypass administrative logs or internal histories
REVOKE ALL ON SCHEMA AUDIT, ADMIN FROM peri_app;

SELECT 'Security profile boundaries locked down under least privilege constraints.' AS status;
