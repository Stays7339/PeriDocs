# ==========================================
# database_management/storage_engines/postgres_engine.py
# Save-state: 2026-06-22T15:14-04:00
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

    async def load_ledger_bundle(self) -> Dict[str, Any]:
        """
        Rehydrates the authoritative ledger state from the relational database.
        Targets the strict 'ledger' schema namespace.
        """
        state = {
            "next_centroid_id": 1,
            "next_event_index": 1,
            "issued_suffixes": {},
            "events": [],
        }

        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                # 1. Fetch from authoritative ledger schema counters table
                await cur.execute(
                    """
                    SELECT next_centroid_id, next_event_index, issued_suffixes
                    FROM ledger.runtime_counters
                    WHERE system_lock = 'X';
                    """
                )
                row = await cur.fetchone()
                if row:
                    state["next_centroid_id"] = row[0]
                    state["next_event_index"] = row[1]
                    state["issued_suffixes"] = (
                        row[2] if isinstance(row[2], dict) else json.loads(row[2] or "{}")
                    )

                # 2. Fetch all sequence records from the append-only event spine
                await cur.execute(
                    """
                    SELECT payload
                    FROM ledger.events
                    ORDER BY event_index ASC;
                    """
                )
                event_rows = await cur.fetchall()
                for r in event_rows:
                    evt = r[0]
                    if isinstance(evt, str):
                        evt = json.loads(evt)
                    state["events"].append(evt)

        return state

    async def save_ledger_bundle(self, state: Dict[str, Any]) -> None:
        """
        Flushes global counters and appends structural history logs back to 
        the authoritative ledger schema.
        """
        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    # 1. Update Global Status Row in ledger.runtime_counters
                    await cur.execute(
                        """
                        INSERT INTO ledger.runtime_counters (system_lock, next_centroid_id, next_event_index, issued_suffixes)
                        VALUES ('X', %s, %s, %s)
                        ON CONFLICT (system_lock) DO UPDATE SET
                            next_centroid_id = EXCLUDED.next_centroid_id,
                            next_event_index = EXCLUDED.next_event_index,
                            issued_suffixes = EXCLUDED.issued_suffixes;
                        """,
                        (
                            state["next_centroid_id"],
                            state["next_event_index"],
                            json.dumps(state["issued_suffixes"]),
                        ),
                    )

                    # 2. Re-synchronize event trails cleanly 
                    # (Adjust this block if your engine appends incrementally or uses a delta strategy)
                    await cur.execute("TRUNCATE TABLE ledger.events;")
                    for event in state["events"]:
                        await cur.execute(
                            """
                            INSERT INTO ledger.events (event_index, event_type, payload)
                            VALUES (%s, %s, %s);
                            """,
                            (
                                event["event_index"],
                                event["type"],
                                json.dumps(event),
                            ),
                        )

    async def load_entries_bundle(self) -> Dict[str, Any]:
        """
        Rehydrates wholesale entries and their multi-dimensional NLP tensor 
        projections from content.entries, public.entry_mean_embeddings, and public.entry_windows.
        """
        entries_cache = {}
        mean_embeddings = {}
        window_embeddings = {}
        window_text = {}
        standout_window_flags = {}

        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                # 1. Fetch core text metadata from content schema
                await cur.execute(
                    """
                    SELECT entry_id, entry_nickname, timestamp, user_id, safe_text, 
                           centroids, ip_hash, encrypted_raw_ip, encrypted_raw_text, 
                           crisis_flag, hash_from_token_for_deleting_entries
                    FROM content.entries;
                    """
                )
                for row in await cur.fetchall():
                    eid = row[0]
                    entries_cache[eid] = {
                        "entry_id": eid,
                        "entry_nickname": row[1],
                        "timestamp": row[2].isoformat() if row[2] else None,
                        "user_id": row[3],
                        "safe_text": row[4],
                        "centroids": row[5] if isinstance(row[5], list) else json.loads(row[5] or "[]"),
                        "ip_hash": row[6],
                        "encrypted_raw_ip": row[7],
                        "encrypted_raw_text": row[8],
                        "crisis_flag": row[9],
                        "hash_from_token_for_deleting_entries": row[10],
                    }

                # 2. Fetch 1D mean embeddings
                await cur.execute("SELECT entry_id, mean_embedding FROM public.entry_mean_embeddings;")
                for row in await cur.fetchall():
                    mean_embeddings[row[0]] = np.array(row[1], dtype=np.float32)

                # 3. Fetch sequential window matrices reconstructed chronologically
                await cur.execute(
                    """
                    SELECT entry_id, window_embedding, window_text, standout_flag
                    FROM public.entry_windows
                    ORDER BY entry_id, window_index ASC;
                    """
                )
                
                # Group sliding windows by entry_id dynamically
                for row in await cur.fetchall():
                    eid, w_embed, t_val, f_val = row
                    
                    if eid not in window_embeddings:
                        window_embeddings[eid] = []
                        window_text[eid] = []
                        standout_window_flags[eid] = []
                        
                    window_embeddings[eid].append(w_embed)
                    window_text[eid].append(t_val)
                    standout_window_flags[eid].append(f_val)

                # Convert window lists into structured NumPy matrices for the runtime
                for eid in window_embeddings:
                    window_embeddings[eid] = np.array(window_embeddings[eid], dtype=np.float32)
                    window_text[eid] = np.array(window_text[eid], dtype=object)
                    standout_window_flags[eid] = np.array(standout_window_flags[eid], dtype=bool)

        return {
            "entries": entries_cache,
            "mean_embeddings": mean_embeddings,
            "window_embeddings": window_embeddings,
            "window_text": window_text,
            "standout_window_flags": standout_window_flags,
        }

    async def save_entries_bundle(self, bundle: Dict[str, Any]) -> None:
        """
        Flushes entry registries and vector arrays out to relational tables atomically.
        """
        entries = bundle.get("entries", {})
        mean_embeds = bundle.get("mean_embeddings", {})
        win_embeds = bundle.get("window_embeddings", {})
        win_texts = bundle.get("window_text", {})
        win_flags = bundle.get("standout_window_flags", {})

        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    # Clear volatile structures cleanly before writing modern frames
                    await cur.execute("TRUNCATE TABLE public.entry_windows CASCADE;")
                    await cur.execute("TRUNCATE TABLE public.entry_mean_embeddings CASCADE;")
                    await cur.execute("TRUNCATE TABLE content.entries CASCADE;")

                    # 1. Flush entries
                    for eid, entry in entries.items():
                        await cur.execute(
                            """
                            INSERT INTO content.entries (
                                entry_id, entry_nickname, timestamp, user_id, safe_text, centroids,
                                ip_hash, encrypted_raw_ip, encrypted_raw_text, crisis_flag, 
                                hash_from_token_for_deleting_entries
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                            """,
                            (
                                eid, entry.get("entry_nickname"), entry.get("timestamp"),
                                entry.get("user_id"), entry.get("safe_text"), json.dumps(entry.get("centroids", [])),
                                entry.get("ip_hash"), entry.get("encrypted_raw_ip"), entry.get("encrypted_raw_text"),
                                entry.get("crisis_flag", False), entry.get("hash_from_token_for_deleting_entries")
                            )
                        )

                    # 2. Flush Mean Embeddings (convert NumPy arrays back to plain python lists for PG storage)
                    for eid, arr in mean_embeds.items():
                        if isinstance(arr, np.ndarray):
                            await cur.execute(
                                """
                                INSERT INTO public.entry_mean_embeddings (entry_id, mean_embedding)
                                VALUES (%s, %s);
                                """,
                                (eid, arr.tolist())
                            )

                    # 3. Flush Zipped Sliding Windows
                    for eid in win_embeds:
                        embed_matrix = win_embeds[eid]
                        text_vector = win_texts.get(eid, [])
                        flag_vector = win_flags.get(eid, [])
                        
                        if not isinstance(embed_matrix, np.ndarray):
                            continue
                            
                        for idx in range(len(embed_matrix)):
                            w_arr = embed_matrix[idx].tolist()
                            t_val = str(text_vector[idx]) if idx < len(text_vector) else ""
                            f_val = bool(flag_vector[idx]) if idx < len(flag_vector) else False
                            
                            await cur.execute(
                                """
                                INSERT INTO public.entry_windows (entry_id, window_index, window_embedding, window_text, standout_flag)
                                VALUES (%s, %s, %s, %s, %s);
                                """,
                                (eid, idx, w_arr, t_val, f_val)
                            )

    async def load_centroids_bundle(self) -> Dict[str, Any]:
        """
        Rehydrates active coordinate maps and history trails from the search schema namespace.
        """
        centroids_cache = {}
        states_log = []

        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                # 1. Gather primary structural summaries
                await cur.execute("SELECT centroid_id, title_from_human_moderator, description_from_human_moderator FROM search.centroids;")
                for row in await cur.fetchall():
                    cid = row[0]
                    centroids_cache[cid] = {
                        "centroid_id": cid,
                        "title_from_human_moderator": row[1],
                        "description_from_human_moderator": row[2],
                        "coordinate_matrix": None, 
                        "assigned_points": []
                    }

                # 2. Extract detailed tracking sequences to wire up back to the memory runtime
                await cur.execute(
                    """
                    SELECT centroid_id, event_index, entry_ids, vector, metadata
                    FROM search.centroid_states
                    ORDER BY event_index ASC;
                    """
                )
                for row in await cur.fetchall():
                    cid, idx, entry_ids, vector, meta = row
                    meta_dict = meta if isinstance(meta, dict) else json.loads(meta or "{}")
                    
                    states_log.append({
                        "centroid_id": cid,
                        "event_index": idx,
                        "entry_ids": entry_ids,
                        "vector": vector,
                        "metadata": meta_dict
                    })
                    
                    # Update active in-memory cache projections with the most recent transaction state
                    if cid in centroids_cache:
                        centroids_cache[cid]["coordinate_matrix"] = vector
                        centroids_cache[cid]["assigned_points"] = entry_ids

        return {
            "centroids_cache": centroids_cache,
            "states_log": states_log
        }

    async def save_centroids_bundle(self, bundle: Dict[str, Any]) -> None:
        """
        Saves cluster locations and audit entries down to search.centroids and search.centroid_states.
        """
        cache = bundle.get("centroids_cache", {})
        log = bundle.get("states_log", [])

        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    await cur.execute("TRUNCATE TABLE search.centroids CASCADE;")

                    # 1. Persist master indices
                    for cid, obj in cache.items():
                        await cur.execute(
                            """
                            INSERT INTO search.centroids (centroid_id, title_from_human_moderator, description_from_human_moderator)
                            VALUES (%s, %s, %s);
                            """,
                            (cid, obj.get("title_from_human_moderator"), obj.get("description_from_human_moderator"))
                        )

                    # 2. Persist step logs
                    for step in log:
                        vector_data = step["vector"]
                        if isinstance(vector_data, np.ndarray):
                            vector_data = vector_data.tolist()

                        await cur.execute(
                            """
                            INSERT INTO search.centroid_states (centroid_id, event_index, entry_ids, vector, metadata)
                            VALUES (%s, %s, %s, %s, %s);
                            """,
                            (
                                step["centroid_id"],
                                step["event_index"],
                                list(step["entry_ids"]),
                                vector_data,
                                json.dumps(step.get("metadata", {}))
                            )
                        )