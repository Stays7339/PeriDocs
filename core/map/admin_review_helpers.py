# ==========================================
# core/map/admin_review_helpers.py
# save-state updated 202512231656
# ==========================================
import os
import uuid
import json
import hashlib
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
import asyncio
import numpy as np
from core.map import centroids

from sklearn.cluster import AgglomerativeClustering
import aiofiles

logger = logging.getLogger("peridocs.review")
logger.setLevel(logging.INFO)

REVIEW_QUEUE: Dict[str, Dict[str, Any]] = {}
CENTROID_DIR = centroids.CENTROID_DIR
REVIEW_FILE_TEMPLATE = "review_queue_{yearmonth}.npz"
JOURNALS_FILE = os.path.join(CENTROID_DIR, "journals.json")
LAST_REFRESH_FILE = os.path.join(CENTROID_DIR, "review_last_refresh.json")

_cached_journal_entries: Optional[List[Dict[str, Any]]] = None
MAX_LABEL_CHARS = 100
MAX_NOTE_CHARS = 1000

def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"

def current_review_file() -> str:
    ym = datetime.utcnow().strftime("%Y%m")
    return os.path.join(
        CENTROID_DIR,
        REVIEW_FILE_TEMPLATE.format(yearmonth=ym)
    )

# ---------------- Journal Loading ----------------
async def _load_journal_entries() -> List[Dict[str, Any]]:
    global _cached_journal_entries
    if _cached_journal_entries is not None:
        return _cached_journal_entries
    if not os.path.exists(JOURNALS_FILE):
        _cached_journal_entries = []
        return []
    try:
        async with aiofiles.open(JOURNALS_FILE, "r", encoding="utf-8") as f:
            content = await f.read()
            _cached_journal_entries = json.loads(content)
            return _cached_journal_entries
    except Exception as e:
        logger.warning(f"Failed to load journals.json: {e}")
        _cached_journal_entries = []
        return []

# ---------------- Persistence ----------------
async def save_review_queue(file_path: Optional[str] = None):
    if file_path is None:
        file_path = current_review_file()
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    await asyncio.to_thread(np.savez, file_path, review_queue=REVIEW_QUEUE)
    logger.info(f"Review queue saved to {file_path}")

async def load_review_queue(file_path: Optional[str] = None):
    global REVIEW_QUEUE
    if file_path is None:
        file_path = current_review_file()
    if os.path.exists(file_path):
        data = await asyncio.to_thread(np.load, file_path, allow_pickle=True)
        REVIEW_QUEUE = dict(data["review_queue"].item())
        logger.info(f"Loaded review queue from {file_path}")
        return

    prev_month = (
        datetime.utcnow().replace(day=1) - np.timedelta64(1, "D")
    ).strftime("%Y%m")
    prev_file = os.path.join(
        CENTROID_DIR,
        REVIEW_FILE_TEMPLATE.format(yearmonth=prev_month)
    )
    if os.path.exists(prev_file):
        data = await asyncio.to_thread(np.load, prev_file, allow_pickle=True)
        REVIEW_QUEUE = dict(data["review_queue"].item())
        logger.info(f"Carried over review queue from {prev_file}")
    else:
        REVIEW_QUEUE = {}
        logger.info("No review queue found; starting empty.")

# ---------------- Precentroid ID / Candidate Detection ----------------
def _stable_precentroid_id(entry: Dict[str, Any]) -> str:
    dom_emotion = entry.get("dominant_emotion", "None")
    embedding_str = json.dumps(entry.get("embedding", ""))
    cluster_string = dom_emotion + embedding_str
    md5hash = hashlib.md5(cluster_string.encode()).hexdigest()
    return f"precentroid_{md5hash}"

async def find_candidate_centroid_ids(since_timestamp: Optional[str] = None) -> List[str]:
    entries = await _load_journal_entries()
    candidate_map: Dict[str, List[Dict[str, Any]]] = {}
    for e in entries:
        assigned = e.get("centroid_id")
        entry_ts = e.get("timestamp")
        if assigned is None or assigned == "suggest_new_centroid":
            if since_timestamp is None or entry_ts > since_timestamp:
                pre_id = _stable_precentroid_id(e)
                candidate_map.setdefault(pre_id, []).append(e)

    # Merge highly similar precentroids
    merged_map: Dict[str, List[Dict[str, Any]]] = {}
    keys = list(candidate_map.keys())
    visited = set()
    for i, k1 in enumerate(keys):
        if k1 in visited:
            continue
        cluster_entries = candidate_map[k1]
        visited.add(k1)
        for k2 in keys[i+1:]:
            if k2 in visited:
                continue
            vec1 = np.mean([np.array(e.get("embedding", [0]*1024)) for e in cluster_entries], axis=0)
            vec2 = np.mean([np.array(e.get("embedding", [0]*1024)) for e in candidate_map[k2]], axis=0)
            sim = np.dot(vec1, vec2) / (np.linalg.norm(vec1)*np.linalg.norm(vec2) + 1e-8)
            if sim > 0.95:
                cluster_entries.extend(candidate_map[k2])
                visited.add(k2)
        merged_map[k1] = cluster_entries
    return list(merged_map.keys())

# ---------------- Review Queue ----------------
async def add_review_suggestion(
    *,
    centroid_id: str,
    suggestion_type: str,
    metrics: Dict[str, Any],
    save: bool = True
) -> str:
    # Avoid duplicates
    for existing in REVIEW_QUEUE.values():
        if existing["centroid_id"] == centroid_id and existing["suggestion_type"] == suggestion_type:
            return existing["suggestion_id"]

    suggestion_id = str(uuid.uuid4())
    REVIEW_QUEUE[suggestion_id] = {
        "suggestion_id": suggestion_id,
        "centroid_id": centroid_id,
        "suggestion_type": suggestion_type,
        "metrics": metrics,
        "created_at": _now_iso(),
        "status": "pending",
        "human_note": None,
        "human_labels": [],
        "human_labels_ledger": [],
    }
    if save:
        await save_review_queue()
    return suggestion_id

# ---------------- Explicit Human Mutations ----------------
async def update_review_status(
    suggestion_id: str,
    *,
    status: str,
    note: Optional[str] = None
) -> Optional[str]:
    if suggestion_id not in REVIEW_QUEUE:
        raise KeyError("Unknown suggestion_id")
    cid = REVIEW_QUEUE[suggestion_id]["centroid_id"]

    flash = None
    if note and len(note) > MAX_NOTE_CHARS:
        flash = f"Human note exceeds {MAX_NOTE_CHARS} characters and was not saved."
        note = note[:MAX_NOTE_CHARS]

    if status == "accepted" and cid not in centroids.CENTROIDS:
        await centroids.create_centroid_from_precentroid(cid)

    if status == "rejected":
        await recluster_rejected_precentroid(cid, similarity_threshold=0.92)

    REVIEW_QUEUE[suggestion_id]["status"] = status
    if note is not None:
        REVIEW_QUEUE[suggestion_id]["human_note"] = note
    await save_review_queue()
    return flash

async def update_review_labels(suggestion_id: str, labels: List[str]) -> Optional[str]:
    if suggestion_id not in REVIEW_QUEUE:
        raise KeyError("Unknown suggestion_id")

    flash = None
    for idx, label in enumerate(labels):
        if len(label) > MAX_LABEL_CHARS:
            flash = f"One or more labels exceed {MAX_LABEL_CHARS} characters and were truncated."
            labels[idx] = label[:MAX_LABEL_CHARS]

    ledger = REVIEW_QUEUE[suggestion_id].get("human_labels_ledger", [])
    ledger.append(labels)
    REVIEW_QUEUE[suggestion_id]["human_labels_ledger"] = ledger
    REVIEW_QUEUE[suggestion_id]["human_labels"] = labels

    await save_review_queue()
    return flash

# ---------------- Review Queue Listing ----------------
async def list_review_queue(status: Optional[str] = None) -> List[Dict[str, Any]]:
    items = list(REVIEW_QUEUE.values())
    if status:
        items = [i for i in items if i["status"] == status]

    for i in items:
        cid = i["centroid_id"]
        i["samples"] = await centroids.get_journal_entry_samples_for_centroid(cid)
        i["centroid_exists"] = cid in centroids.CENTROIDS

    return sorted(items, key=lambda x: x["created_at"])

# ---------------- Helpers for Enqueuing Centroid Suggestions ----------------
async def enqueue_split_suggestions(watch_threshold: float = 0.85, since_timestamp: Optional[str] = None) -> List[str]:
    out_ids = []
    suggestions = await centroids.suggest_split_candidates(watch_threshold=watch_threshold)
    for s in suggestions:
        out_ids.append(await add_review_suggestion(
            centroid_id=s["centroid_id"],
            suggestion_type="split_centroid",
            metrics={
                "drift_score": s["drift_score"],
                "count": s["count"],
                "avg_variance": s["avg_variance"],
            },
            save=False
        ))
    return out_ids

# ---------------- Semantic Reclustering Gate ----------------
async def recluster_rejected_precentroid(
    rejected_precentroid_id: str,
    similarity_threshold: float = 0.92
) -> list[str]:
    candidate_texts = await centroids.load_candidate_journal_entries_for_precentroid(
        rejected_precentroid_id
    )
    if not candidate_texts:
        logger.warning(f"No candidate entries found for reclustering {rejected_precentroid_id}")
        return []

    embedding_fn = await centroids.get_embedding_function()
    candidate_vectors = np.stack(await asyncio.gather(
        *[embedding_fn(text) for text in candidate_texts]
    ))

    norms = np.linalg.norm(candidate_vectors, axis=1, keepdims=True) + 1e-8
    norm_vectors = candidate_vectors / norms
    similarity_matrix = np.dot(norm_vectors, norm_vectors.T)
    distance_matrix = 1.0 - similarity_matrix

    clustering = AgglomerativeClustering(
        n_clusters=None,
        affinity='precomputed',
        linkage='complete',
        distance_threshold=1.0 - similarity_threshold
    )
    labels = clustering.fit_predict(distance_matrix)

    new_precentroid_ids = []
    journal_entries = await _load_journal_entries()

    for lbl in np.unique(labels):
        subgroup_texts = [candidate_texts[i] for i in range(len(candidate_texts)) if labels[i] == lbl]
        if not subgroup_texts:
            continue

        combined_hash = hashlib.md5("".join(subgroup_texts).encode()).hexdigest()
        new_id = f"precentroid_{combined_hash}"

        for entry in journal_entries:
            nlp_data = entry.setdefault("nlp", {})
            assigned_id = nlp_data.get("assigned_centroid_id")
            if assigned_id == rejected_precentroid_id and entry.get("safe_text") in subgroup_texts:
                nlp_data["assigned_centroid_id"] = new_id

        new_precentroid_ids.append(new_id)

    try:
        async with aiofiles.open(centroids.JOURNALS_FILE, "w", encoding="utf-8") as f:
            await f.write(json.dumps(journal_entries, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.warning(f"Failed to save journals after reclustering: {e}")

    logger.info(
        f"Reclustered rejected precentroid {rejected_precentroid_id} "
        f"into {len(new_precentroid_ids)} new precentroids"
    )
    return new_precentroid_ids

# ---------------- Initialize / Refresh Queue ----------------
async def refresh_review_queue():
    await load_review_queue()

    last_refresh_ts = None
    if os.path.exists(LAST_REFRESH_FILE):
        try:
            async with aiofiles.open(LAST_REFRESH_FILE, "r", encoding="utf-8") as f:
                last_refresh_ts = json.loads(await f.read()).get("last_refresh")
        except Exception as e:
            logger.warning(f"Failed to read last refresh timestamp: {e}")

    added = False

    split_ids = await enqueue_split_suggestions(since_timestamp=last_refresh_ts)
    if split_ids:
        added = True

    candidate_ids = await find_candidate_centroid_ids(since_timestamp=last_refresh_ts)
    for cid in candidate_ids:
        if any(v["centroid_id"] == cid and v["suggestion_type"] == "new_centroid"
               for v in REVIEW_QUEUE.values()):
            continue
        await add_review_suggestion(
            centroid_id=cid,
            suggestion_type="new_centroid",
            metrics={
                "candidate_count": len(await centroids.get_journal_entry_samples_for_centroid(cid)),
            },
            save=False
        )
        added = True

    if added:
        await save_review_queue()
        logger.info("Review queue incrementally updated with new split or centroid suggestions.")

    try:
        async with aiofiles.open(LAST_REFRESH_FILE, "w", encoding="utf-8") as f:
            await f.write(json.dumps({"last_refresh": _now_iso()}))
    except Exception as e:
        logger.warning(f"Failed to update last refresh timestamp: {e}")

async def initialize_review_queue():
    await load_review_queue()
    await refresh_review_queue()
    logger.info("Review queue initialized and refreshed on startup.")
