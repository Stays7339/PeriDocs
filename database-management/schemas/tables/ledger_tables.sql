-- ============================================================================
-- PERIDOCS SCHEMAS: LEDGER SCHEMA & DETERMINISTIC EVENT TRAIL
-- Location: database-management/schemas/tables/ledger_tables.sql
-- ============================================================================

BEGIN;

-- 1. Ensure the schema namespace container exists physically in the catalog
CREATE SCHEMA IF NOT EXISTS ledger;

-- 2. Append-only authoritative historical validation spine
CREATE TABLE IF NOT EXISTS ledger.events (
    event_index INT PRIMARY KEY,
    event_type  VARCHAR(64) NOT NULL, 
    payload     JSONB NOT NULL,        
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ledger_events_type ON ledger.events(event_type);

-- 3. Authoritative Ledger Runtime Counters (Aligned with validator target)
CREATE TABLE IF NOT EXISTS ledger.runtime_counters (
    system_lock        CHAR(1) PRIMARY KEY DEFAULT 'X',
    next_centroid_id   INT NOT NULL DEFAULT 1,
    next_event_index   INT NOT NULL DEFAULT 1,
    issued_suffixes    JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at         TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT single_row_enforcement CHECK (system_lock = 'X')
);

-- 4. Authorize the application runtime role to interact with the new domain
GRANT USAGE ON SCHEMA ledger TO peri_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ledger TO peri_app;

COMMIT;