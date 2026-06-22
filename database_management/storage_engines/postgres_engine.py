# ==========================================
# database_management/storage_engines/postgres_engine.py
# Save-state: 2026-06-17T16:59-04:00
# ==========================================
import io
import json
import logging
from datetime import datetime, timezone
import numpy as np
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class PostgresStorageEngine:
    def __init__(self, pool):
        self.pool = pool

    def _serialize_numpy(self, arr: np.ndarray | None) -> bytes | None:
        if arr is None or not isinstance(arr, np.ndarray):
            return None
        buf = io.BytesIO()
        np.save(buf, arr)
        return buf.getvalue()

    async def save_ledger_bundle(self, state: Dict[str, Any]) -> None:
        """Flushes global counters and appends structural history logs."""
        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    # 1. Update Global Status Row
                    await cur.execute(
                        """
                        INSERT INTO public.ledger_counters (system_lock, next_centroid_id, next_event_index, issued_suffixes)
                        VALUES ('X', %s, %s, %s)
                        ON CONFLICT (system_lock) DO UPDATE SET
                            next_centroid_id = EXCLUDED.next_centroid_id,
                            next_event_index = EXCLUDED.next_event_index,
                            issued_suffixes = EXCLUDED.issued_suffixes,
                            updated_at = CURRENT_TIMESTAMP;
                        """,
                        (state["next_centroid_id"], state["next_event_index"], json.dumps(state["issued_suffixes"]))
                    )
                    
                    # 2. Bulk Sync Event Sequence History Logs
                    event_query = """
                        INSERT INTO public.ledger_events (event_index, event_type, payload, occurred_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (event_index) DO NOTHING;
                    """
                    event_params = [
                        (
                            ev["event_index"],
                            ev["type"],
                            json.dumps(ev),
                            ev.get("occurred_at", datetime.now(timezone.utc).isoformat())
                        )
                        for ev in state.get("events", [])
                    ]
                    if event_params:
                        await cur.executemany(event_query, event_params)

    async def save_entries_bundle(
        self, 
        entries_cache: List[Dict[str, Any]], 
        mean_embeddings_cache: Dict[str, np.ndarray],
        window_embeddings_cache: Dict[str, np.ndarray],
        window_text_cache: Dict[str, Any],
        standout_window_flags_cache: Dict[str, np.ndarray]
    ) -> None:
        """
        Obediently serializes and upserts the complete sequential in-memory 
        state into Postgres row-by-row for resource-optimized views.
        """
        query = """
            INSERT INTO public.entries (
                entry_id, metadata, mean_embedding, window_embeddings, window_text, standout_flags
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (entry_id) DO UPDATE SET
                metadata = EXCLUDED.metadata,
                mean_embedding = EXCLUDED.mean_embedding,
                window_embeddings = EXCLUDED.window_embeddings,
                window_text = EXCLUDED.window_text,
                standout_flags = EXCLUDED.standout_flags,
                updated_at = CURRENT_TIMESTAMP;
        """
        params = []
        for entry in entries_cache:
            eid = entry.get("entry_id")
            if not eid:
                continue
            
            mean_embed = mean_embeddings_cache.get(eid)
            mean_embed_list = mean_embed.tolist() if isinstance(mean_embed, np.ndarray) else None
            
            params.append((
                eid,
                json.dumps(entry),
                mean_embed_list,
                self._serialize_numpy(window_embeddings_cache.get(eid)),
                json.dumps(window_text_cache.get(eid, {})),
                self._serialize_numpy(standout_window_flags_cache.get(eid))
            ))
        
        if params:
            async with self.pool.connection() as conn:
                async with conn.transaction():
                    async with conn.cursor() as cur:
                        await cur.executemany(query, params)
                        logger.info(f"[Postgres Engine] Successfully checkpointed {len(params)} rows.")


    async def load_entries_bundle(self) -> Dict[str, Any]:
        """
        Queries the database and reconstructs the sequential, in-memory structures
        required by EntryWritingRuntime on startup.
        """
        entries_cache = []
        mean_embeddings_cache = {}
        window_embeddings_cache = {}
        window_text_cache = {}
        standout_window_flags_cache = {}

        query = """
            SELECT entry_id, metadata, mean_embedding, window_embeddings, window_text, standout_flags 
            FROM public.entries
            ORDER BY created_at ASC;  -- Keeps sequence order intact
        """
        
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query)
                rows = await cur.fetchall()
                
                for row in rows:
                    eid = row[0]
                    metadata = row[1] if isinstance(row[1], dict) else json.loads(row[1])
                    mean_embed = np.array(row[2]) if row[2] else None
                    
                    # De-serialize clause window binaries back into live NumPy arrays
                    window_embed = np.load(io.BytesIO(row[3])) if row[3] else None
                    window_text = row[4] if isinstance(row[4], dict) else json.loads(row[4] or "{}")
                    standout_flags = np.load(io.BytesIO(row[5])) if row[5] else None

                    entries_cache.append(metadata)
                    if mean_embed is not None:
                        mean_embeddings_cache[eid] = mean_embed
                    if window_embed is not None:
                        window_embeddings_cache[eid] = window_embed
                    if window_text:
                        window_text_cache[eid] = window_text
                    if standout_flags is not None:
                        standout_window_flags_cache[eid] = standout_flags

        return {
            "entries_cache": entries_cache,
            "mean_embeddings_cache": mean_embeddings_cache,
            "window_embeddings_cache": window_embeddings_cache,
            "window_text_cache": window_text_cache,
            "standout_window_flags_cache": standout_window_flags_cache
        }
    
    async def save_centroids_bundle(
        self,
        centroids_cache: Dict[str, Any],       # Flattened centroid definitions
        states_log: List[Dict[str, Any]],       # Historical c.states records
        split_suggestions: Dict[str, Any]       # self._split_suggestions
    ) -> None:
        """
        Obediently persists the entire in-memory clustering architecture 
        without performing any vector calculations or state logic inside SQL.
        """
        centroid_query = """
            INSERT INTO public.centroids (centroid_id, mean_embedding, metadata)
            VALUES (%s, %s, %s)
            ON CONFLICT (centroid_id) DO UPDATE SET
                mean_embedding = EXCLUDED.mean_embedding,
                metadata = EXCLUDED.metadata,
                updated_at = CURRENT_TIMESTAMP;
        """
        
        state_query = """
            INSERT INTO public.centroid_states (event_index, centroid_id, state_data)
            VALUES (%s, %s, %s)
            ON CONFLICT (event_index, centroid_id) DO NOTHING;  -- Audit logs are immutable
        """

        # Serialize and bundle the items cleanly for executemany calls
        centroid_params = [
            (cid, data["mean_embedding"].tolist(), json.dumps(data["metadata"]))
            for cid, data in centroids_cache.items()
        ]
        
        state_params = [
            (s["event_index"], s["centroid_id"], json.dumps(s["state_data"]))
            for s in states_log
        ]

        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    if centroid_params:
                        await cur.executemany(centroid_query, centroid_params)
                    if state_params:
                        await cur.executemany(state_query, state_params)
                        
                    # Save split suggestions wholesale into a centralized system config/state table
                    await cur.execute(
                        """
                        INSERT INTO public.system_state (key, payload)
                        VALUES ('split_suggestions', %s)
                        ON CONFLICT (key) DO UPDATE SET payload = EXCLUDED.payload;
                        """,
                        (json.dumps(split_suggestions),)
                    )
                    logger.info("[Postgres Engine] Successfully checkpointed centroid system states.")
    
    async def load_centroids_bundle(self) -> Dict[str, Any]:
        """
        Obediently re-hydrates the entire centroid system from database states.
        Converts vector elements back to live NumPy arrays and reconstructs
        historical timeline mappings for the core CentroidSystem memory caches.
        """
        centroids_cache = {}
        states_log = []
        split_suggestions = {}

        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                # 1. Re-hydrate the active Centroids and their Mean Embeddings
                await cur.execute(
                    """
                    SELECT centroid_id, mean_embedding, metadata 
                    FROM public.centroids;
                    """
                )
                centroid_rows = await cur.fetchall()
                for row in centroid_rows:
                    cid = row[0]
                    # Convert PostgreSQL vector array/list back to an operational NumPy float array
                    mean_embed = np.array(row[1], dtype=np.float32) if row[1] else None
                    metadata = row[2] if isinstance(row[2], dict) else json.loads(row[2] or "{}")
                    
                    centroids_cache[cid] = {
                        "mean_embedding": mean_embed,
                        "metadata": metadata
                    }

                # 2. Re-hydrate the chronological immutable structural history states
                await cur.execute(
                    """
                    SELECT event_index, centroid_id, state_data 
                    FROM public.centroid_states
                    ORDER BY event_index ASC;
                    """
                )
                state_rows = await cur.fetchall()
                for row in state_rows:
                    state_data = row[2] if isinstance(row[2], dict) else json.loads(row[2] or "{}")
                    states_log.append({
                        "event_index": row[0],
                        "centroid_id": row[1],
                        "state_data": state_data
                    })

                # 3. Pull down wholesale split suggestions config payload
                await cur.execute(
                    """
                    SELECT payload 
                    FROM public.system_state 
                    WHERE key = 'split_suggestions';
                    """
                )
                suggestion_row = await cur.fetchone()
                if suggestion_row and suggestion_row[0]:
                    payload = suggestion_row[0]
                    split_suggestions = payload if isinstance(payload, dict) else json.loads(payload)

        logger.info(
            "[Postgres Engine] Loaded bundle: %d centroids, %d state log history records.",
            len(centroids_cache),
            len(states_log)
        )

        return {
            "centroids_cache": centroids_cache,
            "states_log": states_log,
            "split_suggestions": split_suggestions
        }