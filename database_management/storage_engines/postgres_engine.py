# ============================================================================
# database_management/storage_engines/postgres_engine.py
# Save-state: 2026-07-12T09:02-04:00
# ============================================================================
import json
import logging
from datetime import datetime, timezone
import numpy as np
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class PostgresStorageEngine:
    def __init__(self, pool):
        self.pool = pool

    # ------------------------------------------------------------------------
    # LEDGER STORAGE COMPONENT (ledger_schema.sql Alignment)
    # ------------------------------------------------------------------------
    async def load_ledger_bundle(self) -> Dict[str, Any]:
        """
        Rehydrates the authoritative ledger state from the relational database.
        Targets the isolated 'ledger' schema namespace and deterministic event trail.
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
                    # High-Level Protection: Handle both dictionary and tuple row formats safely
                    if isinstance(row, dict):
                        state["next_centroid_id"] = row.get("next_centroid_id", 1)
                        state["next_event_index"] = row.get("next_event_index", 1)
                        suffixes_raw = row.get("issued_suffixes")
                    else:
                        state["next_centroid_id"] = row[0]
                        state["next_event_index"] = row[1]
                        suffixes_raw = row[2]

                    state["issued_suffixes"] = (
                        suffixes_raw if isinstance(suffixes_raw, dict) 
                        else json.loads(suffixes_raw or "{}")
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
                    # Safe extraction whether 'r' is a dict entry or a tuple element
                    evt = r.get("payload") if isinstance(r, dict) else r[0]
                    if isinstance(evt, str):
                        evt = json.loads(evt)
                    state["events"].append(evt)

        return state

    async def save_ledger_bundle(self, state: Dict[str, Any]) -> None:
        """
        Flushes global counters and appends structural history logs back to 
        the authoritative ledger schema. Mirrors flat-file rewrite tendencies.
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

                    # 2. Re-synchronize event trails cleanly (Mirroring full file rewrites)
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
        projections natively from the unified content schema.
        """
        entries_list = []
        mean_embeddings = {}
        raw_window_embeddings = {}
        raw_window_text = {}
        raw_standout_window_flags = {}

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
                    if isinstance(row, dict):
                        eid = row.get("entry_id")
                        entries_list.append({
                            "entry_id": eid,
                            "entry_nickname": row.get("entry_nickname"),
                            "timestamp": row.get("timestamp").isoformat() if row.get("timestamp") else None,
                            "user_id": row.get("user_id"),
                            "safe_text": row.get("safe_text"),
                            "centroids": row.get("centroids") if isinstance(row.get("centroids"), list) else json.loads(row.get("centroids") or "[]"),
                            "ip_hash": row.get("ip_hash"),
                            "encrypted_raw_ip": row.get("encrypted_raw_ip"),
                            "encrypted_raw_text": row.get("encrypted_raw_text"),
                            "crisis_flag": row.get("crisis_flag"),
                            "hash_from_token_for_deleting_entries": row.get("hash_from_token_for_deleting_entries"),
                        })
                    else:
                        eid = row[0]
                        entries_list.append({
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
                        })

                # 2. Simplified: Fetch 1D mean embeddings directly by entry_id (1-Dimensional Array, only has width)
                await cur.execute("SELECT entry_id, embedding FROM content.embeddings;")
                for row in await cur.fetchall():
                    if isinstance(row, dict):
                        mean_embeddings[row["entry_id"]] = np.array(row["embedding"], dtype=np.float32)
                    else:
                        mean_embeddings[row[0]] = np.array(row[1], dtype=np.float32)

                # 3. Fetch sequential window matrices chronologically
                await cur.execute(
                    """
                    SELECT entry_id, window_embedding, window_text, standout_flag
                    FROM content.entry_windows
                    ORDER BY entry_id, window_index ASC;
                    """
                )
                for row in await cur.fetchall():
                    if isinstance(row, dict):
                        eid = row["entry_id"]
                        w_embed = row["window_embedding"]
                        t_val = row["window_text"]
                        f_val = row["standout_flag"]
                    else:
                        eid, w_embed, t_val, f_val = row
                        
                    if eid not in raw_window_embeddings:
                        raw_window_embeddings[eid] = []
                        raw_window_text[eid] = []
                        raw_standout_window_flags[eid] = []
                        
                    raw_window_embeddings[eid].append(w_embed)
                    raw_window_text[eid].append(t_val)
                    raw_standout_window_flags[eid].append(f_val)

        # Enforce unified key space structure across all dictionary projections
        window_embeddings = {}
        window_text = {}
        window_flags = {}

        for entry in entries_list:
            eid = entry["entry_id"]
            if eid not in mean_embeddings:
                mean_embeddings[eid] = np.array([], dtype=np.float32)

            if eid in raw_window_embeddings:
                window_embeddings[eid] = np.array(raw_window_embeddings[eid], dtype=np.float32)
                window_text[eid] = np.array(raw_window_text[eid], dtype=object)
                window_flags[eid] = np.array(raw_standout_window_flags[eid], dtype=bool)
            else:
                window_embeddings[eid] = np.empty((0, 1024), dtype=np.float32)
                window_text[eid] = np.array([], dtype=object)
                window_flags[eid] = np.array([], dtype=bool)

        return {
            "entries": entries_list,
            "embeddings": mean_embeddings,          
            "window_embeddings": window_embeddings,
            "window_text": window_text,
            "window_flags": window_flags,           
        }

    async def save_entries_bundle(
        self, 
        snapshot: list, 
        embedding_snapshot: dict, 
        window_embeddings: dict, 
        window_text: dict, 
        standout_flags: dict
    ) -> None:
        """
        Intercepts the runtime's full flush request and runs a streamlined,
        transactional batch synchronization across all content tables.
        """
        # 1. Delegate core text data insertion and deletion tracking to our snapshot mechanism
        await self.sync_entries_snapshot(snapshot)

        # Extract active entry IDs from the snapshot to ensure we only process living vectors
        active_entry_ids = {entry["entry_id"] for entry in snapshot if "entry_id" in entry}

        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    
                    # --------------------------------------------------------
                    # PHASE 1: Synchronize High-Dimensional Master Vectors
                    # --------------------------------------------------------
                    for entry_id, raw_vector in embedding_snapshot.items():
                        # Structural Visibility Guard: Bypass deleted or uninitialized states
                        if entry_id not in active_entry_ids or raw_vector is None or len(raw_vector) == 0:
                            continue

                        vector_payload = raw_vector.tolist() if hasattr(raw_vector, "tolist") else list(raw_vector)
                        
                        await cur.execute(
                            """
                            INSERT INTO content.embeddings (entry_id, embedding)
                            VALUES (%s, %s)
                            ON CONFLICT (entry_id) DO NOTHING;
                            """,
                            (entry_id, vector_payload)
                        )

                    # --------------------------------------------------------
                    # PHASE 2: Synchronize Granular Sliding Window Text Chunks
                    # --------------------------------------------------------
                    for entry_id, w_embeds in window_embeddings.items():
                        # Structural Visibility Guard
                        if entry_id not in active_entry_ids or w_embeds is None or len(w_embeds) == 0:
                            continue

                        w_texts = window_text.get(entry_id, [])
                        w_flags = standout_flags.get(entry_id, [])

                        for idx in range(len(w_embeds)):
                            current_vector = w_embeds[idx].tolist() if hasattr(w_embeds[idx], "tolist") else list(w_embeds[idx])
                            current_text = w_texts[idx] if idx < len(w_texts) else ""
                            current_flag = bool(w_flags[idx]) if idx < len(w_flags) else False

                            await cur.execute(
                                """
                                INSERT INTO content.entry_windows (
                                    entry_id, window_index, window_embedding, window_text, standout_flag
                                ) VALUES (%s, %s, %s, %s, %s)
                                ON CONFLICT (entry_id, window_index) DO UPDATE SET
                                    window_text = EXCLUDED.window_text,
                                    standout_flag = EXCLUDED.standout_flag;
                                """,
                                (entry_id, idx, current_vector, current_text, current_flag)
                            )

        logger.debug("[DB SYNC] Vector and text window matrices successfully synchronized.")


    async def sync_entries_snapshot(self, memory_entries: list[dict[str, Any]]) -> None:
        """
        Syncs the database tables to perfectly mirror the authoritative in-memory state.
        This handles inserts, updates, and deletes in a single write-behind operation.
        """
        # Step 1: Extract all active deletion tokens currently in memory
        active_tokens = [
            entry["hash_from_token_for_deleting_entries"] 
            for entry in memory_entries 
            if "hash_from_token_for_deleting_entries" in entry
        ]

        # Step 2: Extract all active text content hashes (entry_ids) currently in memory
        active_entry_ids = list(set(
            entry["entry_id"] 
            for entry in memory_entries 
            if "entry_id" in entry
        ))

        # Open a single database connection and transaction block
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                try:
                    # --------------------------------------------------------
                    # PHASE A: REMOVE DELETED DATA
                    # --------------------------------------------------------
                    
                    # Wipe any entry rows from the database if their token hash is no longer in memory
                    # Using '= ANY(%s)' is highly efficient and safe for passing lists to Postgres
                    await cur.execute(
                        """
                        DELETE FROM content.entries 
                        WHERE NOT (hash_from_token_for_deleting_entries = ANY(%s));
                        """,
                        (active_tokens,)
                    )
                    
                    # Wipe shared vectors if their entry_id is completely missing from memory.
                    # Thanks to your 'ON DELETE CASCADE' rule, this single command also 
                    # instantly cleans up all orphaned text slices in the entry_windows table.
                    await cur.execute(
                        """
                        DELETE FROM content.embeddings 
                        WHERE NOT (entry_id = ANY(%s));
                        """,
                        (active_entry_ids,)
                    )

                    # --------------------------------------------------------
                    # PHASE B: UPSERT ACTIVE DATA
                    # --------------------------------------------------------
                    
                    # Save or update the remaining entries that are still alive in memory
                    for entry in memory_entries:
                        # Extract the data fields cleanly from the dictionary template
                        entry_id = entry["entry_id"]
                        nickname = entry.get("entry_nickname")
                        timestamp = entry["timestamp"]
                        user_id = entry.get("user_id")
                        safe_text = entry.get("safe_text", "")
                        centroids = json.dumps(entry.get("centroids", []))
                        ip_hash = entry.get("ip_hash")
                        enc_ip = entry.get("encrypted_raw_ip")
                        enc_text = entry.get("encrypted_raw_text")
                        crisis_flag = bool(entry.get("crisis_flag", False))
                        token_hash = entry["hash_from_token_for_deleting_entries"]

                        # Write the entry to the main content tracking table
                        # If the row already exists, update its data fields automatically
                        await cur.execute(
                            """
                            INSERT INTO content.entries (
                                entry_id, entry_nickname, timestamp, user_id, safe_text, 
                                centroids, ip_hash, encrypted_raw_ip, encrypted_raw_text, 
                                crisis_flag, hash_from_token_for_deleting_entries
                            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
                            ON CONFLICT (hash_from_token_for_deleting_entries) 
                            DO UPDATE SET 
                                entry_nickname = EXCLUDED.entry_nickname,
                                safe_text = EXCLUDED.safe_text,
                                centroids = EXCLUDED.centroids,
                                crisis_flag = EXCLUDED.crisis_flag,
                                updated_at = CURRENT_TIMESTAMP;
                            """,
                            (
                                entry_id, nickname, timestamp, user_id, safe_text, 
                                centroids, ip_hash, enc_ip, enc_text, 
                                crisis_flag, token_hash
                            )
                        )

                    logger.debug(
                        f"[DB SYNC] Successfully mirrored {len(memory_entries)} entries. "
                        f"Cleaned up orphaned entries and vectors."
                    )

                except Exception as e:
                    # Log the exact error and cancel the transaction to keep the database clean
                    logger.exception(f"[DB SYNC] Failed to execute write-behind replication: {e}")
                    raise e

    # ------------------------------------------------------------------------
    # CENTROIDS STORAGE COMPONENT (search_schema.sql Alignment)
    # ------------------------------------------------------------------------
    async def load_centroids_bundle(self) -> Dict[str, Any]:
        """
        Rehydrates all centroids and precentroids from relational storage.
        Transforms flat database rows from the search schema into the specialized 
        nested dictionary structure expected by core/map/centroids.py.
        """
        centroids_map = {}

        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                # 1. Fetch core centroid metadata definitions from the search schema
                await cur.execute(
                    """
                    SELECT centroid_id, title_from_human_moderator, description_from_human_moderator
                    FROM search.centroids;
                    """
                )
                for row in await cur.fetchall():
                    if isinstance(row, dict):
                        cid = row["centroid_id"]
                        title = row["title_from_human_moderator"]
                        desc = row["description_from_human_moderator"]
                    else:
                        cid = row[0]
                        title = row[1]
                        desc = row[2]
                        
                    centroids_map[cid] = {
                        "centroid_id": cid,
                        "title_from_human_moderator": title,
                        "description_from_human_moderator": desc,
                        "states": {}  # Legacyside expects a lookup dictionary keyed by event_index
                    }

                # 2. Fetch historical state records ordered chronologically
                await cur.execute(
                    """
                    SELECT centroid_id, event_index, entry_ids, vector, metadata
                    FROM search.centroid_states
                    ORDER BY centroid_id, event_index ASC;
                    """
                )
                for row in await cur.fetchall():
                    if isinstance(row, dict):
                        cid = row["centroid_id"]
                        ev_idx = row["event_index"]
                        entry_ids = row["entry_ids"]
                        vector = row["vector"]
                        metadata = row["metadata"]
                    else:
                        cid, ev_idx, entry_ids, vector, metadata = row
                    
                    if cid in centroids_map:
                        # Rehydrate the vector array back to a proper NumPy structure
                        np_vector = np.array(vector, dtype=np.float32) if vector else np.array([], dtype=np.float32)
                        
                        # entry_ids is native TEXT[], psycopg unpacks it as a standard python list
                        parsed_entries = entry_ids if isinstance(entry_ids, list) else json.loads(entry_ids or "[]")
                        
                        # metadata is JSONB, handled defensively if returned as string or pre-parsed dict
                        parsed_metadata = metadata if isinstance(metadata, dict) else json.loads(metadata or "{}")

                        # Inject the state into the dictionary using event_index as the lookup key
                        centroids_map[cid]["states"][ev_idx] = {
                            "event_index": ev_idx,
                            "entry_ids": parsed_entries,
                            "vector": np_vector,
                            "metadata": parsed_metadata
                        }

        return centroids_map

    async def save_centroid_bundle(
        self,
        centroid_id: str,
        summary_payload: Dict[str, Any],
        npz_dump: Dict[str, Any]
    ) -> None:
        """
        Commits or updates a single centroid definition and its complete 
        chronological state history array objects into search schema storage.
        Accepts parameters directly from core/map/centroids.py's database branch.
        """
        title = summary_payload.get("title_from_human_moderator")
        description = summary_payload.get("description_from_human_moderator")
        states = summary_payload.get("states", [])

        # Defensive check: if the application state layer passes back a dictionary 
        # keyed by event_index, extract the raw state objects sequentially.
        if isinstance(states, dict):
            states_iterable = states.values()
        else:
            states_iterable = states

        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    # 1. Upsert the master centroid metadata registry row
                    await cur.execute(
                        """
                        INSERT INTO search.centroids (
                            centroid_id, 
                            title_from_human_moderator, 
                            description_from_human_moderator
                        ) VALUES (%s, %s, %s)
                        ON CONFLICT (centroid_id) DO UPDATE SET
                            title_from_human_moderator = EXCLUDED.title_from_human_moderator,
                            description_from_human_moderator = EXCLUDED.description_from_human_moderator;
                        """,
                        (centroid_id, title, description)
                    )

                    # 2. Clear existing historical state rows ONLY for this specific cluster ID
                    await cur.execute(
                        "DELETE FROM search.centroid_states WHERE centroid_id = %s;",
                        (centroid_id,)
                    )

                    # 3. Stream sequential records back down to the state tracking layout
                    for state in states_iterable:
                        ev_idx = state["event_index"]
                        entry_ids = state["entry_ids"]
                        vec = state["vector"]
                        metadata = state["metadata"]

                        # Ensure array properties match Postgres text array expectations perfectly
                        entry_ids_list = entry_ids if isinstance(entry_ids, list) else list(entry_ids)
                        vec_list = vec.tolist() if isinstance(vec, np.ndarray) else list(vec)
                        
                        # Prepare dictionary structures for target JSONB injection
                        metadata_string = json.dumps(metadata) if isinstance(metadata, dict) else metadata

                        await cur.execute(
                            """
                            INSERT INTO search.centroid_states (
                                centroid_id, event_index, entry_ids, vector, metadata
                            ) VALUES (%s, %s, %s, %s, %s::jsonb);
                            """,
                            (
                                centroid_id, 
                                ev_idx, 
                                entry_ids_list, 
                                vec_list, 
                                metadata_string
                            )
                        )