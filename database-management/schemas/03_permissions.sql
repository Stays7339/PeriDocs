-- ====================================================================
-- PeriDocs RADICLE v0 - Access Control Matrix & Permissions
-- ====================================================================

-- Step 1: Wipe default public inheritance parameters on schemas to harden the cluster
REVOKE ALL ON SCHEMA public FROM PUBLIC;

-- Step 2: Establish the Structural Engineer (migrator) Rights
GRANT USAGE, CREATE ON SCHEMA content, kb, search, inference, nlp, audit, admin, app TO migrator;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA content, kb, search, inference, nlp, audit, admin, app TO migrator;

-- Step 3: Establish Content Steward (curator) Limitations
GRANT USAGE ON SCHEMA content, kb, search, nlp, audit TO curator;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA content, kb TO curator;
GRANT SELECT ON ALL TABLES IN SCHEMA search, nlp, audit TO curator;

-- Step 4: Establish Independent Reviewer (auditor) Rights
GRANT USAGE ON SCHEMA audit, admin, nlp, content, kb TO auditor;
GRANT SELECT ON ALL TABLES IN SCHEMA audit, admin, nlp, content, kb TO auditor;

-- Step 5: Establish System Governor (admin) Rights
GRANT USAGE, CREATE ON SCHEMA admin TO admin;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA admin TO admin;
GRANT USAGE ON SCHEMA audit, nlp, content, kb, app TO admin;
GRANT SELECT ON ALL TABLES IN SCHEMA audit, nlp, content, kb, app TO admin;

-- Step 6: Secure the FastAPI Application Runtime (peri_app)
GRANT USAGE ON SCHEMA app, inference, content, kb, search, nlp TO peri_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app, inference TO peri_app;
GRANT SELECT ON ALL TABLES IN SCHEMA content, kb, search, nlp TO peri_app;
REVOKE ALL ON SCHEMA audit, admin FROM peri_app;

SELECT 'Security profile boundaries locked down under least privilege constraints.' AS status;