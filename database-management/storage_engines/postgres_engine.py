# ==========================================
# database-management/storage_engines/postgres_engine.py
# Save-state: 2026-06-14T15:27-04:00
# ==========================================
import json
import logging
import numpy as np
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class PostgresStorageEngine:
    def __init__(self, pool):
        """
        Assumes an initialized async connection pool (e.g., psycopg_pool.AsyncConnectionPool)
        passed down from core/database.py's pool manager.
        """
        self.pool = pool

    async def save_entries_bundle(
        self, 
        snapshot: List[Dict[str, Any]], 
        embedding_snapshot: Dict[str, np.ndarray],
        window_embeddings: Dict[str, np.ndarray],
        window_text: Dict[str, Any],
        standout_flags: Dict[str, np.ndarray]
    ) -> None:
        """
        Atomically flushes the comprehensive core entry ledger text and multi-state 
        NLP matrix tensors to content_tables.sql and nlp_tables.sql.
        """
        async with self.pool.connection() as conn:
            # Open an explicit atomic transaction block
            async with conn.transaction():
                async with conn.cursor() as cur:
                    
                    # 1. UPSERT INTO public.entries (Structured JSON Data)
                    entries_query = """
                        INSERT INTO public.entries (
                            entry_id, entry_nickname, timestamp, user_id, safe_text, 
                            centroids, ip_hash, encrypted_raw_ip, encrypted_raw_text, 
                            crisis_flag, hash_from_token_for_deleting_entries
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (entry_id) DO UPDATE SET
                            entry_nickname = EXCLUDED.entry_nickname,
                            safe_text = EXCLUDED.safe_text,
                            centroids = EXCLUDED.centroids,
                            crisis_flag = EXCLUDED.crisis_flag,
                            updated_at = CURRENT_TIMESTAMP;
                    """
                    
                    entries_params = [
                        (
                            e["entry_id"],
                            e.get("entry_nickname"),
                            e["timestamp"],
                            e["user_id"],
                            e.get("safe_text"),
                            json.dumps(e.get("centroids", [])),
                            e.get("ip_hash"),
                            e.get("encrypted_raw_ip"),
                            e.get("encrypted_raw_text"),
                            e.get("crisis_flag", False),
                            e.get("hash_from_token_for_deleting_entries")
                        )
                        for e in snapshot
                    ]
                    await cur.executemany(entries_query, entries_params)

                    # 2. UPSERT INTO public.entry_mean_embeddings (Dense 1024-float arrays)
                    mean_query = """
                        INSERT INTO public.entry_mean_embeddings (entry_id, mean_embedding)
                        VALUES (%s, %s)
                        ON CONFLICT (entry_id) DO UPDATE SET
                            mean_embedding = EXCLUDED.mean_embedding,
                            updated_at = CURRENT_TIMESTAMP;
                    """
                    
                    mean_params = []
                    for entry_id, vector in embedding_snapshot.items():
                        if isinstance(vector, np.ndarray):
                            # Convert NumPy array to vanilla Python float list for REAL[] compatibility
                            mean_params.append((entry_id, vector.tolist()))
                    
                    if mean_params:
                        await cur.executemany(mean_query, mean_params)

                    # 3. OVERWRITE SEQUENCE FOR public.entry_windows (Sliding Window Series)
                    for entry_id in window_embeddings.keys():
                        # To support variable length shifts across runtime executions, 
                        # we purge old window sequences and re-insert the parallel arrays atomically.
                        await cur.execute("DELETE FROM public.entry_windows WHERE entry_id = %s;", (entry_id,))
                        
                        embeds_matrix = window_embeddings[entry_id]      # Expected Shape: (N, 1024)
                        txt_list = window_text.get(entry_id, [])          # Expected Length: N
                        flags_array = standout_flags.get(entry_id, [])    # Expected Length: N
                        
                        # Validate parallel shapes before building parameters
                        N = len(embeds_matrix)
                        window_params = []
                        for idx in range(N):
                            w_vector = embeds_matrix[idx].tolist()
                            w_text = txt_list[idx] if idx < len(txt_list) else ""
                            w_flag = bool(flags_array[idx]) if idx < len(flags_array) else False
                            
                            window_params.append((entry_id, idx, w_vector, w_text, w_flag))
                        
                        if window_params:
                            window_insert_query = """
                                INSERT INTO public.entry_windows (
                                    entry_id, window_index, window_embedding, window_text, standout_flag
                                ) VALUES (%s, %s, %s, %s, %s);
                            """
                            await cur.executemany(window_insert_query, window_params)

        logger.debug("[POSTGRES ENGINE] save_entries_bundle transaction completed successfully.")

    async def save_centroid_bundle(self, centroid_id: str, summary_payload: Dict[str, Any], npz_dump: Dict[str, np.ndarray]) -> None:
        """
        Atomically flushes single-cluster mutation profiles and evolutionary historical states 
        to kb_tables.sql.
        """
        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    
                    # 1. UPSERT INTO public.centroids (Root Identifiers)
                    centroid_query = """
                        INSERT INTO public.centroids (centroid_id, title_from_human_moderator, description_from_human_moderator)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (centroid_id) DO UPDATE SET
                            title_from_human_moderator = COALESCE(EXCLUDED.title_from_human_moderator, public.centroids.title_from_human_moderator),
                            description_from_human_moderator = COALESCE(EXCLUDED.description_from_human_moderator, public.centroids.description_from_human_moderator);
                    """
                    await cur.execute(
                        centroid_query, 
                        (
                            centroid_id, 
                            summary_payload.get("title_from_human_moderator"), 
                            summary_payload.get("description_from_human_moderator")
                        )
                    )

                    # 2. UPSERT INTO public.centroid_states & public.centroid_state_members
                    state_query = """
                        INSERT INTO public.centroid_states (centroid_id, event_index, vector, metadata)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (centroid_id, event_index) DO UPDATE SET
                            vector = EXCLUDED.vector,
                            metadata = EXCLUDED.metadata;
                    """
                    
                    # Iterate over chronological timeline states found inside the payload serialization
                    for state_idx, state_data in enumerate(summary_payload.get("states", [])):
                        event_index = state_data.get("event_index")
                        if event_index is None:
                            continue
                        
                        # Match the exact key schema layout constructed in your runtime loop
                        vector_key = f"{centroid_id}_state{state_idx}"
                        vector = npz_dump.get(vector_key)
                        
                        if vector is None or not isinstance(vector, np.ndarray):
                            raise RuntimeError(f"[Postgres Engine] Missing matrix vector for key: {vector_key}")
                        
                        # Isolate state dictionary configurations
                        state_metadata = state_data.get("metadata", {})
                        
                        await cur.execute(
                            state_query,
                            (centroid_id, event_index, vector.tolist(), json.dumps(state_metadata))
                        )
                        
                        # 3. SYNC MEMBERSHIP JUNCTION MATRIX
                        # Purge old allocations for this specific event snapshot to absorb membership alterations cleanly
                        await cur.execute(
                            "DELETE FROM public.centroid_state_members WHERE centroid_id = %s AND event_index = %s;",
                            (centroid_id, event_index)
                        )
                        
                        # Extract the array of entry IDs associated with this cluster state snapshot
                        member_entries = state_data.get("entry_ids", [])
                        if member_entries:
                            member_query = """
                                INSERT INTO public.centroid_state_members (centroid_id, event_index, entry_id)
                                VALUES (%s, %s, %s)
                                ON CONFLICT DO NOTHING;
                            """
                            member_params = [(centroid_id, event_index, eid) for eid in member_entries]
                            await cur.executemany(member_query, member_params)

        logger.debug("[POSTGRES ENGINE] save_centroid_bundle for %s completed successfully.", centroid_id)
    
    async def load_entries_bundle(self) -> Dict[str, Any]:
        """
        Queries content_tables.sql and nlp_tables.sql to fully rehydrate
        the EntryWritingRuntime memory caches in a single pass.
        """
        logger.info("[POSTGRES ENGINE] Initiating entry bundle rehydration query...")
        
        bundle = {
            "entries": [],
            "embeddings": {},
            "window_embeddings": {},
            "window_text": {},
            "standout_flags": {}
        }
        
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                
                # 1. Fetch all root JSON entries
                await cur.execute("""
                    SELECT 
                        entry_id, entry_nickname, timestamp, user_id, safe_text, 
                        centroids, ip_hash, encrypted_raw_ip, encrypted_raw_text, 
                        crisis_flag, hash_from_token_for_deleting_entries
                    FROM public.entries;
                """)
                
                async for row in cur:
                    # Reconstruct the exact dictionary keys expected by entry_runtime
                    entry_dict = {
                        "entry_id": row[0],
                        "entry_nickname": row[1],
                        "timestamp": row[2].isoformat() if row[2] else None,
                        "user_id": row[3],
                        "safe_text": row[4],
                        "centroids": row[5] if isinstance(row[5], list) else json.loads(row[5] or "[]"),
                        "ip_hash": row[6],
                        "encrypted_raw_ip": row[7],
                        "encrypted_raw_text": row[8],
                        "crisis_flag": row[9],
                        "hash_from_token_for_deleting_entries": row[10]
                    }
                    bundle["entries"].append(entry_dict)
                
                # 2. Fetch all dense Mean Embeddings
                await cur.execute("SELECT entry_id, mean_embedding FROM public.entry_mean_embeddings;")
                async handle in cur:
                    async for row in cur:
                        # Re-wrap native float lists back into canonical float32 NumPy shapes
                        bundle["embeddings"][row[0]] = np.array(row[1], dtype=np.float32)
                
                # 3. Fetch sliding window sequences grouped by entry_id
                await cur.execute("""
                    SELECT entry_id, window_index, window_embedding, window_text, standout_flag
                    FROM public.entry_windows
                    ORDER BY entry_id, window_index ASC;
                """)
                
                # Temporary groupings to stitch zipped database rows back into arrays
                temp_windows = {}
                async for row in cur:
                    eid, idx, w_embed, w_text, w_flag = row
                    if eid not in temp_windows:
                        temp_windows[eid] = {"embeds": [], "texts": [], "flags": []}
                    
                    temp_windows[eid]["embeds"].append(w_embed)
                    temp_windows[eid]["texts"].append(w_text)
                    temp_windows[eid]["flags"].append(w_flag)
                
                # Convert the sequences into tightly aligned sequence matrices
                for eid, structures in temp_windows.items():
                    bundle["window_embeddings"][eid] = np.array(structures["embeds"], dtype=np.float32)
                    bundle["window_text"][eid] = np.array(structures["texts"], dtype=str)
                    bundle["standout_flags"][eid] = np.array(structures["flags"], dtype=bool)
                    
        logger.info("[POSTGRES ENGINE] Entry bundle rehydration extracted successfully.")
        return bundle


    async def load_centroids_bundle(self) -> Dict[str, Any]:
        """
        Queries kb_tables.sql to extract and aggregate raw database rows 
        into structures ready for CentroidSystem state objects.
        """
        logger.info("[POSTGRES ENGINE] Rehydrating knowledge base matrices...")
        
        raw_centroids = {}
        
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                
                # 1. Fetch root structural configuration profiles
                await cur.execute("SELECT centroid_id, title_from_human_moderator, description_from_human_moderator FROM public.centroids;")
                async for row in cur:
                    cid = row[0]
                    raw_centroids[cid] = {
                        "centroid_id": cid,
                        "title_from_human_moderator": row[1],
                        "description_from_human_moderator": row[2],
                        "states": {}
                    }
                
                # 2. Fetch all evolutionary timeline states
                await cur.execute("SELECT centroid_id, event_index, vector, metadata FROM public.centroid_states ORDER BY centroid_id, event_index ASC;")
                async for row in cur:
                    cid, ev_idx, vec_list, meta_json = row
                    if cid in raw_centroids:
                        meta_dict = meta_json if isinstance(meta_json, dict) else json.loads(meta_json or "{}")
                        raw_centroids[cid]["states"][ev_idx] = {
                            "event_index": ev_idx,
                            "vector": np.array(vec_list, dtype=np.float32),
                            "metadata": meta_dict,
                            "entry_ids": [] # Will be populated by the next query step
                        }
                
                # 3. Fetch membership associations for every historical marker
                await cur.execute("SELECT centroid_id, event_index, entry_id FROM public.centroid_state_members;")
                async for row in cur:
                    cid, ev_idx, eid = row
                    if cid in raw_centroids and ev_idx in raw_centroids[cid]["states"]:
                        raw_centroids[cid]["states"][ev_idx]["entry_ids"].append(eid)
                        
        return raw_centroids

    async def load_ledger_bundle(self) -> Dict[str, Any]:
        """
        Queries ledger_tables.sql to rebuild the authoritative system-wide 
        identity, state-transition, and token ledger mapping.
        """
        logger.info("[POSTGRES ENGINE] Loading ledger configuration state from DB...")
        state = {
            "next_centroid_id": 1,
            "next_event_index": 1,
            "issued_suffixes": {},
            "events": []
        }
        
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                
                # 1. Rehydrate Global System Clock/Indices
                await cur.execute("SELECT next_centroid_id, next_event_index FROM public.ledger_counters WHERE id = 1;")
                row = await cur.fetchone()
                if row:
                    state["next_centroid_id"] = row[0]
                    state["next_event_index"] = row[1]
                else:
                    # Database table is unpopulated (First Boot), insert base configuration primitives
                    await cur.execute("INSERT INTO public.ledger_counters (id, next_centroid_id, next_event_index) VALUES (1, 1, 1);")
                
                # 2. Rehydrate Suffix Allocation History Matrix
                await cur.execute("SELECT suffix_id, kind, reviewed_by_a_human, approved, rejected FROM public.ledger_suffixes;")
                async for row in cur:
                    state["issued_suffixes"][str(row[0])] = {
                        "kind": row[1],
                        "reviewed_by_a_human": row[2],
                        "approved": row[3],
                        "rejected": row[4]
                    }
                    
                # 3. Extract Chronological Audit History Trail Logs
                await cur.execute("SELECT payload FROM public.ledger_events ORDER BY event_index ASC;")
                async for row in cur:
                    # Safely handle JSON parsing fallback variance
                    ev_dict = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
                    state["events"].append(ev_dict)
                    
        return state

    async def save_ledger_bundle(self, state: Dict[str, Any]) -> None:
        """
        Atomically flushes the active in-memory ledger state block down 
        to PostgreSQL using an isolated network transaction sweep.
        """
        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    
                    # 1. UPSERT Global State Sequence Values
                    await cur.execute("""
                        INSERT INTO public.ledger_counters (id, next_centroid_id, next_event_index)
                        VALUES (1, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            next_centroid_id = EXCLUDED.next_centroid_id,
                            next_event_index = EXCLUDED.next_event_index;
                    """, (state["next_centroid_id"], state["next_event_index"]))
                    
                    # 2. BATCH UPSERT Suffix Lifecycle Configurations
                    suffix_query = """
                        INSERT INTO public.ledger_suffixes (suffix_id, kind, reviewed_by_a_human, approved, rejected)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (suffix_id) DO UPDATE SET
                            kind = EXCLUDED.kind,
                            reviewed_by_a_human = EXCLUDED.reviewed_by_a_human,
                            approved = EXCLUDED.approved,
                            rejected = EXCLUDED.rejected,
                            updated_at = CURRENT_TIMESTAMP;
                    """
                    suffix_params = [
                        (
                            int(s_id),
                            meta["kind"],
                            meta["reviewed_by_a_human"],
                            meta["approved"],
                            meta["rejected"]
                        )
                        for s_id, meta in state["issued_suffixes"].items()
                    ]
                    if suffix_params:
                        await cur.executemany(suffix_query, suffix_params)
                        
                    # 3. APPEND NEW EVENTS ONLY (Immutable History Optimization)
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
                        for ev in state["events"]
                    ]
                    if event_params:
                        await cur.executemany(event_query, event_params