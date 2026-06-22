-- ============================================================
--  nlp_tables.sql
-- ============================================================

-- Modified to correctly point to the content schema namespace
CREATE TABLE IF NOT EXISTS public.entry_mean_embeddings (
    entry_id       VARCHAR(64) PRIMARY KEY REFERENCES content.entries(entry_id) ON DELETE CASCADE,
    mean_embedding REAL[] NOT NULL, 
    updated_at     TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.entry_windows (
    entry_id         VARCHAR(64) REFERENCES content.entries(entry_id) ON DELETE CASCADE,
    window_index     INT NOT NULL, 
    window_embedding REAL[] NOT NULL, 
    window_text      TEXT NOT NULL,      
    standout_flag    BOOLEAN NOT NULL,   
    PRIMARY KEY (entry_id, window_index)
);

-- Performance index for chronological sequence rehydration loops
CREATE INDEX IF NOT EXISTS idx_entry_windows_lookup ON public.entry_windows(entry_id, window_index ASC);