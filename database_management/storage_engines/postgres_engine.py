# database_management/storage_engines/postgres_engine.py
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
        snapshot: List[Dict[str, Any]], 
        embedding_snapshot: Dict[str, np.ndarray],
        window_embeddings: Dict[str, np.ndarray],
        window_text: Dict[str, Any],
        standout_flags: Dict[str, np.ndarray]
    ) -> None:
        """Dumps runtime memory tables and tensors directly into flat document rows."""
        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
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
                    for entry in snapshot:
                        eid = entry.get("entry_id")
                        if not eid:
                            continue
                        
                        mean_embed = embedding_snapshot.get(eid)
                        mean_embed_list = mean_embed.tolist() if isinstance(mean_embed, np.ndarray) else None
                        
                        params.append((
                            eid,
                            json.dumps(entry),
                            mean_embed_list,
                            self._serialize_numpy(window_embeddings.get(eid)),
                            json.dumps(window_text.get(eid, {})),
                            self._serialize_numpy(standout_flags.get(eid))
                        ))
                    
                    if params:
                        await cur.executemany(query, params)