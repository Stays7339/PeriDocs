-- ====================================================================
-- PeriDocs RADICLE v0 - Vector Index & Cluster Optimization Storage
-- Location database_management/schemas/tables/centroid_schema.sql
-- save-state 2026-07-13T15:25-04:00
-- ====================================================================

-- Top-level cluster tracking table
CREATE TABLE IF NOT EXISTS centroid.centroids (
    centroid_id VARCHAR(255) PRIMARY KEY, -- e.g., 'centroid_0000000001' or 'precentroid_0000000002'
    title_from_human_moderator TEXT,
    description_from_human_moderator TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Chronological state history table
CREATE TABLE IF NOT EXISTS centroid.centroid_states (
    centroid_id VARCHAR(255) REFERENCES centroid.centroids(centroid_id) ON UPDATE CASCADE ON DELETE CASCADE,
    event_index INT NOT NULL,
    entry_ids TEXT[] NOT NULL,           -- Stores the sorted list of member document IDs
    vector REAL[] NOT NULL,              -- Stores the 1024-dimension float array
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb, -- Stores review statuses and metrics
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (centroid_id, event_index)
);

-- Index the foreign key and event sequence for high-performance timeline lookups
CREATE INDEX IF NOT EXISTS idx_centroid_states_lookup 
ON centroid.centroid_states (centroid_id, event_index DESC);