-- database-management/schemas/tables/ledger_tables.sql
BEGIN;

-- 1. Global Monotonically Increasing System Counters
CREATE TABLE IF NOT EXISTS public.ledger_counters (
    id                 INT PRIMARY KEY DEFAULT 1,
    next_centroid_id   INT NOT NULL DEFAULT 1,
    next_event_index   INT NOT NULL DEFAULT 1,
    CONSTRAINT single_row_enforcement CHECK (id = 1)
);

-- 2. Suffix Governance and Lifecycle Registries
CREATE TABLE IF NOT EXISTS public.ledger_suffixes (
    suffix_id           INT PRIMARY KEY,
    kind                VARCHAR(64) NOT NULL,
    reviewed_by_a_human BOOLEAN NOT NULL DEFAULT FALSE,
    approved            BOOLEAN NOT NULL DEFAULT FALSE,
    rejected            BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 3. Comprehensive Append-Only Deterministic Audit History Trail
CREATE TABLE IF NOT EXISTS public.ledger_events (
    event_index         INT PRIMARY KEY,
    event_type          VARCHAR(64) NOT NULL,
    payload             JSONB NOT NULL, -- Flexible structure to preserve varying metadata across event variants
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ledger_events_type ON public.ledger_events(event_type);

COMMIT;