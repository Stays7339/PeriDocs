# ==========================================
# core/map/admin_review_helpers.py
# save-state 202512271554
# ==========================================
import os
import uuid
import json
import hashlib
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
import asyncio
import aiofiles
from core.map import centroids
from sklearn.cluster import AgglomerativeClustering
import numpy as np

logger = logging.getLogger("peridocs.review")
logger.setLevel(logging.INFO)

REVIEW_QUEUE: Dict[str, Dict[str, Any]] = {}
LAST_REFRESH_FILE = os.path.join(centroids.CENTROID_DIR, "review_last_refresh.json")

MAX_LABEL_CHARS = 100
MAX_NOTE_CHARS = 1000

def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"

# ---------------- Review Queue Persistence ----------------
async def save_review_queue(file_path: Optional[str] = None):
    if file_path is None:
        ym = datetime.utcnow().strftime("%Y%m")
        file_path = os.path.join(centroids.CENTROID_DIR, f"review_queue_{ym}.npz")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    await asyncio.to_thread(np.savez, file_path, review_queue=REVIEW_QUEUE)
    logger.info(f"Review queue saved to {file_path}")

async def load_review_queue(file_path: Optional[str] = None):
    global REVIEW_QUEUE
    if file_path is None:
        ym = datetime.utcnow().strftime("%Y%m")
        file_path = os.path.join(centroids.CENTROID_DIR, f"review_queue_{ym}.npz")
    if os.path.exists(file_path):
        data = await asyncio.to_thread(np.load, file_path, allow_pickle=True)
        REVIEW_QUEUE = dict(data["review_queue"].item())
        logger.info(f"Loaded review queue from {file_path}")
    else:
        REVIEW_QUEUE = {}
        logger.info("No review queue found; starting empty.")

# ---------------- Review Queue CRUD ----------------
async def add_review_suggestion(
    centroid_id: str,
    suggestion_type: str,
    metrics: Dict[str, Any],
    save: bool = True
) -> str:
    for existing in REVIEW_QUEUE.values():
        if existing["centroid_id"] == centroid_id and existing["suggestion_type"] == suggestion_type:
            return existing["suggestion_id"]

    suggestion_id = str(uuid.uuid4())
    REVIEW_QUEUE[suggestion_id] = {
        "suggestion_id": suggestion_id,
        "centroid_id": centroid_id,
        "suggestion_type": suggestion_type,
        "metrics": metrics,
        "status": "pending",
        "human_note": None,
        "human_labels": [],
        "human_labels_ledger": [],
        "created_at": _now_iso(),
    }
    if save:
        await save_review_queue()
    return suggestion_id

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
        flash = f"Human note exceeds {MAX_NOTE_CHARS} characters and was truncated."
        note = note[:MAX_NOTE_CHARS]

    if status == "accepted" and cid.startswith("precentroid_"):
        await centroids.promote_precentroid_to_centroid(precentroid_id=cid)

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
            flash = f"One or more labels exceeded {MAX_LABEL_CHARS} and were truncated."
            labels[idx] = label[:MAX_LABEL_CHARS]

    ledger = REVIEW_QUEUE[suggestion_id].get("human_labels_ledger", [])
    ledger.append(labels)
    REVIEW_QUEUE[suggestion_id]["human_labels_ledger"] = ledger
    REVIEW_QUEUE[suggestion_id]["human_labels"] = labels

    await save_review_queue()
    return flash

# ---------------- Queue Listing ----------------
async def list_review_queue(status: Optional[str] = None) -> List[Dict[str, Any]]:
    items = [v for v in REVIEW_QUEUE.values() if status is None or v["status"] == status]
    for item in items:
        cid = item["centroid_id"]
        item["samples"] = await centroids.get_journal_entry_samples_for_centroid(cid)
        item["centroid_exists"] = cid in centroids.CENTROIDS
    return sorted(items, key=lambda x: x["created_at"])

# ---------------- Candidate Discovery ----------------
def _stable_precentroid_id(entry: Dict[str, Any]) -> str:
    embedding_str = json.dumps(entry.get("embedding", ""))
    return f"precentroid_{hashlib.md5((dom_emotion + embedding_str).encode()).hexdigest()}"

async def find_candidate_centroid_ids(since_timestamp: Optional[str] = None) -> List[str]:
    JOURNALS_FILE = os.path.join(centroids.CENTROID_DIR, "journals.json")
    if not os.path.exists(JOURNALS_FILE):
        return []
    async with aiofiles.open(JOURNALS_FILE, "r", encoding="utf-8") as f:
        all_entries = json.loads(await f.read())

    candidate_map: Dict[str, List[Dict[str, Any]]] = {}
    for e in all_entries:
        assigned = e.get("nlp", {}).get("assigned_centroid_id")
        ts = e.get("timestamp", "")
        if assigned is None or assigned == "suggest_new_centroid":
            if since_timestamp is None or ts > since_timestamp:
                pre_id = _stable_precentroid_id(e)
                candidate_map.setdefault(pre_id, []).append(e)

    # Merge highly similar candidates
    merged: Dict[str, List[Dict[str, Any]]] = {}
    keys = list(candidate_map.keys())
    visited = set()
    for i, k1 in enumerate(keys):
        if k1 in visited:
            continue
        cluster_entries = candidate_map[k1]
        visited.add(k1)
        for k2 in keys[i + 1:]:
            if k2 in visited:
                continue
            vec1 = np.mean([np.array(e.get("embedding", [0]*1024)) for e in cluster_entries], axis=0)
            vec2 = np.mean([np.array(e.get("embedding", [0]*1024)) for e in candidate_map[k2]], axis=0)
            sim = np.dot(vec1, vec2) / (np.linalg.norm(vec1)*np.linalg.norm(vec2) + 1e-8)
            if sim > 0.95:
                cluster_entries.extend(candidate_map[k2])
                visited.add(k2)
        merged[k1] = cluster_entries
    return list(merged.keys())

# ---------------- Queue Refresh ----------------
async def enqueue_split_suggestions(watch_threshold: float = 0.85) -> List[str]:
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

async def refresh_review_queue():
    await load_review_queue()
    added = False

    split_ids = await enqueue_split_suggestions()
    if split_ids:
        added = True

    candidate_ids = await find_candidate_centroid_ids()
    for cid in candidate_ids:
        if any(v["centroid_id"] == cid and v["suggestion_type"] == "new_centroid" for v in REVIEW_QUEUE.values()):
            continue
        await add_review_suggestion(
            centroid_id=cid,
            suggestion_type="new_centroid",
            metrics={"candidate_count": len(await centroids.get_journal_entry_samples_for_centroid(cid))},
            save=False
        )
        added = True

    if added:
        await save_review_queue()

    try:
        async with aiofiles.open(LAST_REFRESH_FILE, "w", encoding="utf-8") as f:
            await f.write(json.dumps({"last_refresh": _now_iso()}))
    except Exception as e:
        logger.warning(f"Failed to update last refresh timestamp: {e}")

async def initialize_review_queue():
    await load_review_queue()
    await refresh_review_queue()
    logger.info("Review queue initialized.")
