-- ====================================================================
-- PeriDocs RADICLE v0 - Multi-Schema Framework Instantiation
-- Location database_management/schemas/02_schemas_init.sql
-- save-state 2026-07-13T14:48-04:00
-- ====================================================================

-- Establish clean structural boundaries to enforce domain separation,
-- ensuring that analytical abstractions do not leak into audit histories.

CREATE SCHEMA IF NOT EXISTS content;     -- Primary Source of Truth (Curated Hypermedia)
CREATE SCHEMA IF NOT EXISTS kb;          -- Ontology & Logic (Concept Schemes & Version Tags)
CREATE SCHEMA IF NOT EXISTS centroid;      -- Retrieval Layer (Functions, Rankings, MatViews)
CREATE SCHEMA IF NOT EXISTS inference;   -- Runtime Interpretations (Query-Specific Maps)
CREATE SCHEMA IF NOT EXISTS audit;       -- Immutable History (Append-Only Modification Logs)
CREATE SCHEMA IF NOT EXISTS admin;       -- Governance Metadata (Release & Actor Privileges)
CREATE SCHEMA IF NOT EXISTS app;         -- User & Session State (Accounts & Safety Hashes)
CREATE SCHEMA IF NOT EXISTS ledger; -- Authoritative Event Ledger

SELECT 'Eight-schema domain framework successfully segmented.' AS status;