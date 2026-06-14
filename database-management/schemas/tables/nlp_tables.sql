-- ============================================================
-- 01. NLP MACHINE LEARNING TENSORS
-- Target File: nlp_tables.sql
-- Description: Mirrors 'entries_mean_embeddings_dump.npz' and sliding windows.
-- ============================================================

-- 2A. Mean Embeddings (1-to-1 extension of entries)
CREATE TABLE IF NOT EXISTS public.entry_mean_embeddings (
    entry_id       VARCHAR(64) PRIMARY KEY REFERENCES public.entries(entry_id) ON DELETE CASCADE,
    mean_embedding REAL[] NOT NULL, -- 1024-dimensional float array invariant
    updated_at     TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2B. Sliding Window Sequence Tables (Handles the shape (N, 1024) and shape (N,) projections)
-- This table structures the parallel zipped rows of:
-- self._window_embeddings, self._window_text, and self._standout_window_flags
CREATE TABLE IF NOT EXISTS public.entry_windows (
    entry_id         VARCHAR(64) REFERENCES public.entries(entry_id) ON DELETE CASCADE,
    window_index     INT NOT NULL, -- The relative chronological order (0 to N-1)
    
    window_embedding REAL[] NOT NULL, -- Map array slice (1024,) from window_embeddings
    window_text      TEXT NOT NULL,      -- Map element from window_text
    standout_flag    BOOLEAN NOT NULL,   -- Map boolean from standout_window_flags
    
    PRIMARY KEY (entry_id, window_index)
);

-- Performance index for chronological sequence rehydration loops
CREATE INDEX IF NOT EXISTS idx_entry_windows_lookup ON public.entry_windows(entry_id, window_index ASC);