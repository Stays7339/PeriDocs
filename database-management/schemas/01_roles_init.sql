-- ====================================================================
-- PeriDocs RADICLE v0 - Role and Identity Provisioning
-- Created: 2026-05-16T13:40:00-04:00 by MB
-- Updated: 2026-05-16T13:40:00-04:00 by MB
-- ====================================================================

-- Securely declare system actors using dynamic anonymous code blocks 
-- to prevent structural failure states during repeat setup execution.

DO $$
BEGIN
    -- 1. System Governor (High-Level Oversight & Security Audits)
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'admin') THEN
        CREATE ROLE admin WITH NOLOGIN;
    END IF;

    -- 2. Structural Engineer (CI/CD Pipeline DDL Implementations)
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'migrator') THEN
        CREATE ROLE migrator WITH NOLOGIN;
    END IF;

    -- 3. Content Steward (Ontology Curators & Taxonomy Providers)
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'curator') THEN
        CREATE ROLE curator WITH NOLOGIN;
    END IF;

    -- 4. Independent Reviewer (Glass-Box Pipeline Auditor)
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'auditor') THEN
        CREATE ROLE auditor WITH NOLOGIN;
    END IF;

    -- 5. Application Service (FastAPI Production Execution Role)
    -- Note: Pre-existing from initial infrastructure provisioning.
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'peri_app') THEN
        CREATE ROLE peri_app WITH LOGIN;
    END IF;
END
$$;

SELECT 'Internal governance roles physicalized idempotently.' AS status;
