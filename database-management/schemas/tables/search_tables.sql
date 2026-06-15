-- ====================================================================
-- PeriDocs RADICLE v0 - Vector Index & Cluster Optimization Storage
-- ====================================================================

-- Top-level cluster tracking table
CREATE TABLE IF NOT EXISTS search.centroids (
    centroid_id VARCHAR(255) PRIMARY KEY, -- e.g., 'centroid_0000000001' or 'precentroid_0000000002'
    title_from_human_moderator TEXT,
    description_from_human_moderator TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Chronological state history table
CREATE TABLE IF NOT EXISTS search.centroid_states (
    centroid_id VARCHAR(255) REFERENCES search.centroids(centroid_id) ON DELETE CASCADE,
    event_index INT NOT NULL,
    entry_ids TEXT[] NOT NULL,           -- Stores the sorted list of member document IDs
    vector REAL[] NOT NULL,              -- Stores the 1024-dimension float array
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb, -- Stores review statuses and metrics
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (centroid_id, event_index)
);

-- Index the foreign key and event sequence for high-performance timeline lookups
CREATE INDEX IF NOT EXISTS idx_centroid_states_lookup 
ON search.centroid_states (centroid_id, event_index DESC);