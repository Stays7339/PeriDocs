# ==========================================
# core/map/admin_review_helpers.py
# save-state 202512171936
# ==========================================
import os
import uuid
import json
import hashlib
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

import numpy as np
from core.map import centroids

logger = logging.getLogger("peridocs.review")
logger.setLevel(logging.INFO)

REVIEW_QUEUE: Dict[str, Dict[str, Any]] = {}
CENTROID_DIR = centroids.CENTROID_DIR
REVIEW_FILE_TEMPLATE = "review_queue_{yearmonth}.npz"
JOURNALS_FILE = os.path.join(CENTROID_DIR, "journals.json")

# ---------------- Cached journal entries ----------------
_cached_journal_entries: Optional[List[Dict[str, Any]]] = None

# ---------------- Character limits ----------------
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


def _load_journal_entries() -> List[Dict[str, Any]]:
    global _cached_journal_entries
    if _cached_journal_entries is not None:
        return _cached_journal_entries
    if not os.path.exists(JOURNALS_FILE):
        _cached_journal_entries = []
        return []
    try:
        with open(JOURNALS_FILE, "r", encoding="utf-8") as f:
            _cached_journal_entries = json.load(f)
            return _cached_journal_entries
    except Exception as e:
        logger.warning(f"Failed to load journals.json: {e}")
        _cached_journal_entries = []
        return []


# ---------------- Persistence ----------------
def save_review_queue(file_path: Optional[str] = None):
    if file_path is None:
        file_path = current_review_file()
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    np.savez(file_path, review_queue=REVIEW_QUEUE)
    logger.info(f"Review queue saved to {file_path}")


def load_review_queue(file_path: Optional[str] = None):
    global REVIEW_QUEUE
    if file_path is None:
        file_path = current_review_file()
    if os.path.exists(file_path):
        data = np.load(file_path, allow_pickle=True)
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
        data = np.load(prev_file, allow_pickle=True)
        REVIEW_QUEUE = dict(data["review_queue"].item())
        logger.info(f"Carried over review queue from {prev_file}")
    else:
        REVIEW_QUEUE = {}
        logger.info("No review queue found; starting empty.")


# ---------------- Core Helpers ----------------
def add_review_suggestion(
    *,
    centroid_id: str,
    suggestion_type: str,
    metrics: Dict[str, Any],
    save: bool = True
) -> str:
    # Avoid duplicate split suggestions
    if suggestion_type == "split_centroid":
        for existing in REVIEW_QUEUE.values():
            if existing["centroid_id"] == centroid_id and existing["suggestion_type"] == "split_centroid":
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
        "human_labels_ledger": [],  # NEW: keeps all previous label sets
    }
    if save:
        save_review_queue()
    return suggestion_id


# ---------------- Candidate Detection ----------------
def _stable_precentroid_id(entry_id: str) -> str:
    md5hash = hashlib.md5(entry_id.encode()).hexdigest()
    return f"precentroid_{md5hash}"


def find_candidate_centroid_ids() -> List[str]:
    entries = _load_journal_entries()
    candidate_ids = set()
    for e in entries:
        assigned = e.get("nlp", {}).get("assigned_centroid_id")
        if assigned is None or assigned == "suggest_new_centroid":
            candidate_ids.add(_stable_precentroid_id(e["id"]))
    return list(candidate_ids)


# ---------------- Review Queue Listing ----------------
def list_review_queue(status: Optional[str] = None) -> List[Dict[str, Any]]:
    items = list(REVIEW_QUEUE.values())
    if status:
        items = [i for i in items if i["status"] == status]

    for i in items:
        cid = i["centroid_id"]
        i["samples"] = centroids.get_journal_entry_samples_for_centroid(cid)
        i["centroid_exists"] = cid in centroids.CENTROIDS

    return sorted(items, key=lambda x: x["created_at"])


def print_review_queue(status: Optional[str] = None):
    items = list_review_queue(status)
    if not items:
        print("No review suggestions.")
        return
    for i in items:
        print(
            f"{i['suggestion_id']} | "
            f"{i['suggestion_type']} | "
            f"centroid={i['centroid_id']} | "
            f"status={i['status']}"
        )


# ---------------- Explicit Human Mutations ----------------
def update_review_status(
    suggestion_id: str,
    *,
    status: str,
    note: Optional[str] = None,
    embedding_fn=None
) -> Optional[str]:
    """
    Returns a flash message string if note too long, else None.
    """
    if suggestion_id not in REVIEW_QUEUE:
        raise KeyError("Unknown suggestion_id")
    cid = REVIEW_QUEUE[suggestion_id]["centroid_id"]

    flash = None
    if note and len(note) > MAX_NOTE_CHARS:
        flash = f"Human note exceeds {MAX_NOTE_CHARS} characters and was not saved."
        note = note[:MAX_NOTE_CHARS]

    if status == "accepted" and cid not in centroids.CENTROIDS:
        centroids.create_centroid_from_precentroid(cid, embedding_fn=embedding_fn)

    REVIEW_QUEUE[suggestion_id]["status"] = status
    if note is not None:
        REVIEW_QUEUE[suggestion_id]["human_note"] = note
    save_review_queue()
    return flash


def update_review_labels(suggestion_id: str, labels: List[str]) -> Optional[str]:
    """
    Update human_labels with char limit and maintain a ledger.
    Returns a flash message string if rejected/trimmed.
    """
    if suggestion_id not in REVIEW_QUEUE:
        raise KeyError("Unknown suggestion_id")

    flash = None
    for idx, label in enumerate(labels):
        if len(label) > MAX_LABEL_CHARS:
            flash = f"One or more labels exceed {MAX_LABEL_CHARS} characters and were truncated."
            labels[idx] = label[:MAX_LABEL_CHARS]

    # Update ledger
    ledger = REVIEW_QUEUE[suggestion_id].get("human_labels_ledger", [])
    ledger.append(labels)
    REVIEW_QUEUE[suggestion_id]["human_labels_ledger"] = ledger
    REVIEW_QUEUE[suggestion_id]["human_labels"] = labels

    save_review_queue()
    return flash


# ---------------- Helpers for Enqueuing Centroid Suggestions ----------------
def enqueue_split_suggestions(watch_threshold: float = 0.85) -> List[str]:
    out_ids = []
    suggestions = centroids.suggest_split_candidates(watch_threshold=watch_threshold)
    for s in suggestions:
        out_ids.append(add_review_suggestion(
            centroid_id=s["centroid_id"],
            suggestion_type="split_centroid",
            metrics={
                "drift_score": s["drift_score"],
                "count": s["count"],
                "avg_variance": s["avg_variance"],
            },
            save=False
        ))
    save_review_queue()
    return out_ids


def initialize_review_queue():
    load_review_queue()
    if REVIEW_QUEUE:
        logger.info("Review queue loaded with existing suggestions.")
        return

    logger.info("Review queue empty; enqueuing new suggestions...")
    enqueue_split_suggestions()

    candidate_ids = find_candidate_centroid_ids()
    for cid in candidate_ids:
        add_review_suggestion(
            centroid_id=cid,
            suggestion_type="new_centroid",
            metrics={
                "candidate_count": len(centroids.get_journal_entry_samples_for_centroid(cid)),
            },
            save=False
        )

    save_review_queue()
    logger.info("Review queue initialized with split and new centroid suggestions.")
