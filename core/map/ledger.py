# ==========================================
# core/map/ledger.py
# save-state 202601021737 (YYYYMMDDhhmm)
# ==========================================
"""

The PeriDocs-code/data/ledger/ directory , alongwith this accompanying python file, is a very import part of the PeriDocs corpus state.

Deleting or modifying files here will break deterministic replay.

The centroid_ledger.json file records the historical issuance
order of centroid and precentroid identifiers.

It must be versioned, backed up, and transported together with
journals and centroid state files. If not, the entire system WILL BREAK; there's no doubt about that.

"""


import os
import json
import hashlib
from typing import List, Dict, Any

DATA_DIR = os.getenv("PERIDOCS_DATA_DIR", "PeriDocs-code/data")
LEDGER_FILE = os.path.join(DATA_DIR, "ledger", "centroid_ledger.json")

# ---------------- Utilities ----------------

def _ensure_dir():
    os.makedirs(os.path.dirname(LEDGER_FILE), exist_ok=True)

def _load_ledger() -> Dict[str, Any]:
    if not os.path.exists(LEDGER_FILE):
        return {"events": [], "corpus_fingerprint": None}
    with open(LEDGER_FILE, "r", encoding="utf-8") as f:
        ledger = json.load(f)
    if "events" not in ledger or not isinstance(ledger["events"], list):
        raise RuntimeError("Ledger corrupted or truncated")
    return ledger

def _save_ledger(ledger: dict) -> None:
    """
    Save ledger to disk and update corpus_fingerprint.

    Uses:
    - CENTROIDS: current state of centroids and precentroids
    - REJECTED_PRECENTROIDS: global set/list of rejected precentroid IDs
    - JOURNALS_FILE: to get journal IDs
    """

    _ensure_dir()

    # ----- Load journal IDs -----
    journal_ids = []
    if os.path.exists(JOURNALS_FILE):
        with open(JOURNALS_FILE, "r", encoding="utf-8") as f:
            journal_ids = sorted(json.load(f).keys())

    # ----- Separate IDs into categories -----
    centroid_ids = sorted(
        cid for cid in CENTROIDS if cid.startswith("centroid_")
    )

    rejected_precentroid_ids = sorted(
        rid for rid in REJECTED_PRECENTROIDS if rid in CENTROIDS
    )

    precentroid_ids = sorted(
        cid for cid in CENTROIDS
        if cid.startswith("precentroid_") and cid not in rejected_precentroid_ids
    )

    # ----- Compute corpus fingerprint -----
    ledger["corpus_fingerprint"] = compute_corpus_fingerprint(
        journal_ids=journal_ids,
        centroid_ids=centroid_ids,
        precentroid_ids=precentroid_ids,
        ledger_events=ledger.get("events", []),
    )

    # ----- Write ledger to disk -----
    with open(LEDGER_FILE, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2, sort_keys=True)


# ---------------- Corpus Fingerprint ----------------

def compute_corpus_fingerprint(
    *,
    journal_ids: list[str],
    centroid_ids: list[str],
    precentroid_ids: list[str],
    ledger_events: list[dict],
) -> str:
    """
    Lightweight determinism fingerprint.
    Order-stable, content-agnostic, replay-safe.
    """
    h = hashlib.sha256()

    def feed(items: list[str]):
        for item in sorted(items):
            h.update(item.encode("utf-8"))
            h.update(b"\0")
        h.update(b"\1")

    feed(journal_ids)
    feed(centroid_ids)
    feed(precentroid_ids)

    for e in ledger_events:
        h.update(str(e.get("id")).encode("utf-8"))
        h.update(b"\0")

    return "sha256:" + h.hexdigest()


def _compute_expected_corpus_fingerprint() -> str:
    from core.map import ledger as ledger_mod

    journal_ids = []
    if os.path.exists(JOURNALS_FILE):
        with open(JOURNALS_FILE, "r", encoding="utf-8") as f:
            journal_ids = sorted(json.load(f).keys())

    centroid_ids = sorted(cid for cid in CENTROIDS if cid.startswith("centroid_"))
    precentroid_ids = sorted(cid for cid in CENTROIDS if cid.startswith("precentroid_"))

    ledger_state = ledger_mod._load_ledger()

    return ledger_mod.compute_corpus_fingerprint(
        journal_ids=journal_ids,
        centroid_ids=centroid_ids,
        precentroid_ids=precentroid_ids,
        ledger_events=ledger_state.get("events", []),
    )


def assert_corpus_fingerprint(expected: str, actual: str) -> None:
    if expected != actual:
        raise RuntimeError(
            "Corpus fingerprint mismatch.\n"
            f"Expected: {expected}\n"
            f"Actual:   {actual}"
        )



# ---------------- Event Log ID Allocation ----------------

def _next_id_from_events(events: List[Dict[str, Any]]) -> int:
    used = {e["id"] for e in events if "id" in e}
    return (max(used) + 1) if used else 1

def allocate_id_if_absent(
    *,
    proposal_fingerprint: str,
    proposal_payload: Dict[str, Any],
) -> int:
    """
    Deterministic, idempotent allocation of a numeric ID for a proposed precentroid.

    If this proposal already exists in the ledger (matching fingerprint),
    returns the existing ID. Otherwise, allocates exactly one new ID,
    appends a 'precentroid_proposed' event to the ledger, persists, and returns it.

    Ensures full compliance with immutable-spec expectations.
    """
    # Load ledger safely
    _ensure_dir()
    if not os.path.exists(LEDGER_FILE):
        ledger = {"events": [], "corpus_fingerprint": None}
    else:
        with open(LEDGER_FILE, "r", encoding="utf-8") as f:
            ledger = json.load(f)

    if "events" not in ledger or not isinstance(ledger["events"], list):
        raise RuntimeError("Ledger corrupted or truncated")

    events = ledger["events"]

    # Check for existing proposal fingerprint
    for e in events:
        if e.get("type") == "precentroid_proposed" and e.get("proposal_fingerprint") == proposal_fingerprint:
            return e["id"]

    # Allocate new deterministic ID
    new_id = _next_id_from_events(events)

    # Append new event
    events.append({
        "type": "precentroid_proposed",
        "id": new_id,
        "proposal_fingerprint": proposal_fingerprint,
        "payload": proposal_payload,
    })

    # Persist updated ledger
    _save_ledger(ledger)

    return new_id
