# ==========================================
# core/map/review_helpers.py
# save-state 202512161749
# ==========================================

"""
Human review queue helpers for centroid suggestions.

Design stance (locked):
- Append-only by default
- Suggestions are records, not intents
- Status changes are inert
- Labels are marginalia, not ontology
- JSON / NPZ safe
"""

import os
import uuid
import numpy as np
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import json

from core.map import centroids  # <-- import centroids.py for samples + enqueue helpers

# ---------------- Logging ----------------
logger = logging.getLogger("peridocs.review")
logger.setLevel(logging.INFO)

# ---------------- In-Memory State ----------------
REVIEW_QUEUE: Dict[str, Dict[str, Any]] = {}

# ---------------- File Handling ----------------
CENTROID_DIR = "data"
REVIEW_FILE_TEMPLATE = "review_queue_{yearmonth}.npz"
JOURNALS_FILE = os.path.join(CENTROID_DIR, "journals.json")  # live journal entries fallback


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def current_review_file() -> str:
    ym = datetime.utcnow().strftime("%Y%m")
    return os.path.join(
        CENTROID_DIR,
        REVIEW_FILE_TEMPLATE.format(yearmonth=ym)
    )


# ---------------- Persistence ----------------
def save_review_queue(file_path: Optional[str] = None):
    if file_path is None:
        file_path = current_review_file()

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    np.savez(
        file_path,
        review_queue=REVIEW_QUEUE,
    )

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

    # carry over previous month
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
) -> str:
    """
    Adds an inert suggestion to the review queue.
    NEVER performs any action.
    """
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
    }

    save_review_queue()
    return suggestion_id


def _fallback_get_centroid_samples(centroid_id: str, max_samples: int = 5) -> List[str]:
    """
    Fallback: fetch live journal entries assigned to this centroid from local JSON.
    """
    if not os.path.exists(JOURNALS_FILE):
        return []

    try:
        with open(JOURNALS_FILE, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load journals.json: {e}")
        return []

    samples = []
    for e in entries:
        nlp = e.get("nlp", {})
        if nlp.get("assigned_centroid_id") == centroid_id:
            text = e.get("safe_text", "")
            if text:
                samples.append(text)
        if len(samples) >= max_samples:
            break

    return samples


def list_review_queue(
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Returns all suggestions, optionally filtered by status.
    Includes centroid sample entries for UI display.
    For non-existent centroids, attaches candidate journal entries.
    """
    items = list(REVIEW_QUEUE.values())
    if status:
        items = [i for i in items if i["status"] == status]

    for i in items:
        cid = i["centroid_id"]
        if cid in centroids.CENTROIDS:
            # Always use centroids.py canonical handler
            i["samples"] = centroids.get_centroid_samples(cid)
        else:
            # centroid does not exist yet: candidate entries
            i["samples"] = centroids.get_candidate_entries_for_centroid(cid)


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
):
    if suggestion_id not in REVIEW_QUEUE:
        raise KeyError("Unknown suggestion_id")

    # handle human-approved creation for pre-centroids
    if status == "accepted" and REVIEW_QUEUE[suggestion_id]["centroid_id"] not in centroids.CENTROIDS:
        centroids.create_centroid_from_samples(REVIEW_QUEUE[suggestion_id]["centroid_id"])

    REVIEW_QUEUE[suggestion_id]["status"] = status
    if note is not None:
        REVIEW_QUEUE[suggestion_id]["human_note"] = note

    save_review_queue()


def update_review_labels(
    suggestion_id: str,
    labels: List[str],
):
    """
    Freeform annotation only.
    """
    if suggestion_id not in REVIEW_QUEUE:
        raise KeyError("Unknown suggestion_id")

    REVIEW_QUEUE[suggestion_id]["human_labels"] = labels
    save_review_queue()


# ---------------- Helpers for Enqueuing Centroid Suggestions ----------------
def enqueue_split_suggestions(
    watch_threshold: float = 0.85
) -> List[str]:
    """
    Converts current centroid split suggestions into review queue entries.
    """
    return centroids.enqueue_split_suggestions_for_review(
        watch_threshold=watch_threshold,
        add_review_suggestion_fn=add_review_suggestion
    )
