# =============================================================
# core/nlp/emotion_model.py
# Updated 2025-12-12 — Option C (human-approved merges)
# =============================================================
"""
Deterministic, embedding-driven "emotion" model for PeriDocs.

Design goals implemented here:
- No fixed emotion labels.
- Approved emotion centroids persist to data/approved_embeddings.json.
- Candidate labels are deterministic phrases derived from input text & centroid.
- Candidate labels are stored in monthly candidate_emotions_{YYYYMM}.json.
- Suggest merge_pairs for human review; merging is human-approved.
- Async-safe file IO (uses asyncio.to_thread).
- Deterministic label synthesis (sha256 + vector stable rules).
"""

from __future__ import annotations
from typing import Dict, Optional, Iterable, List, Tuple, Set
import os
import json
import numpy as np
import asyncio
from datetime import datetime
from hashlib import sha256

from core.nlp.embeddings import get_embedding_async

# ------------------------------------------------------------
# Paths & constants
# ------------------------------------------------------------
DATA_DIR = "data"
APPROVED_EMB_PATH = os.path.join(DATA_DIR, "approved_embeddings.json")
CANDIDATE_TMPL = os.path.join(DATA_DIR, "candidate_emotions_{ts}.json")
MERGE_SUGGESTIONS_PATH = os.path.join(DATA_DIR, "merge_suggestions.json")
EMB_DIM = 1024  # must match your embedding model
_LOCK = asyncio.Lock()

# in-memory caches
_PENDING_CANDIDATES: Set[str] = set()
_APPROVED_CACHE: Dict[str, np.ndarray] = {}  # label -> centroid np.array

# ------------------------------------------------------------
# Utilities
# ------------------------------------------------------------
def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

async def _read_json(path: str, default):
    if not os.path.exists(path):
        return default
    return await asyncio.to_thread(lambda: json.load(open(path, "r", encoding="utf-8")))

async def _write_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    await asyncio.to_thread(lambda: json.dump(data, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False))

def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    an = np.linalg.norm(a) + 1e-12
    bn = np.linalg.norm(b) + 1e-12
    return float(np.dot(a, b) / (an * bn))

def _vec_to_hash(vec: np.ndarray) -> str:
    # deterministic fingerprint derived from vector bytes
    h = sha256(vec.tobytes()).hexdigest()
    return h[:8]

# ------------------------------------------------------------
# Deterministic phrase synthesis (no fixed emotion names)
# ------------------------------------------------------------
# Controlled vocabularies (small, stable lists)
_ADJECTIVES = [
    "soft", "hard", "dull", "bright", "muted", "urgent", "steady", "uneasy",
    "calm", "tense", "warm", "cool", "compressed", "expanded", "frayed",
    "light", "heavy", "restless", "grounded", "floating"
]

_NOUNS = [
    "pressure", "drift", "tension", "stillness", "motion", "weight", "tone",
    "push", "pull", "hum", "echo", "trace", "edge", "haze", "pulse"
]

def _synthesize_label_from_vector(vec: np.ndarray, text_seed: Optional[str] = None) -> str:
    """
    Deterministically synthesize a short descriptive phrase from a vector.
    Uses the vector's statistics and an (optional) text seed for further determinism.
    """
    v = np.asarray(vec, dtype=float).flatten()
    # reduce to a small deterministic fingerprint: mean, std, sign pattern, top dims
    mean = float(np.mean(v))
    std = float(np.std(v))
    # sign pattern over first 6 dims
    signs = tuple(1 if x >= 0 else 0 for x in v[:6])
    # hash these deterministic bits together with optional text seed
    m = sha256()
    m.update(f"{mean:.6f}|{std:.6f}|{signs}".encode("utf-8"))
    if text_seed:
        m.update(text_seed.encode("utf-8"))
    digest = m.hexdigest()

    # pick words deterministically
    adj = _ADJECTIVES[int(digest[0:8], 16) % len(_ADJECTIVES)]
    noun = _NOUNS[int(digest[8:16], 16) % len(_NOUNS)]
    # optionally add a qualifier from another slice
    qual = int(digest[16:20], 16) % 3
    if qual == 0:
        label = f"{adj} {noun}"
    elif qual == 1:
        label = f"{noun} of {adj}"
    else:
        label = f"{adj} {noun}"
    # keep labels short and filesystem-safe
    label = label.replace(" ", "_").lower()
    return label

# ------------------------------------------------------------
# Approved embeddings persistence
# ------------------------------------------------------------
async def _load_approved_embeddings() -> Dict[str, np.ndarray]:
    global _APPROVED_CACHE
    _ensure_data_dir()
    raw = await _read_json(APPROVED_EMB_PATH, {})
    cache = {}
    for k, v in raw.items():
        try:
            cache[k] = np.asarray(v, dtype=float).reshape((EMB_DIM,))
        except Exception:
            # skip malformed entries
            continue
    _APPROVED_CACHE = cache
    return cache

async def _save_approved_embeddings(emb_dict: Dict[str, np.ndarray]):
    # convert arrays -> lists
    serial = {k: v.tolist() for k, v in emb_dict.items()}
    await _write_json(APPROVED_EMB_PATH, serial)
    # update in-memory
    for k, v in emb_dict.items():
        _APPROVED_CACHE[k] = v

# ------------------------------------------------------------
# Candidate handling (monthly files)
# ------------------------------------------------------------
def _candidate_filepath_for_now() -> str:
    ts = datetime.utcnow().strftime("%Y%m")
    return CANDIDATE_TMPL.format(ts=ts)

async def load_existing_candidates() -> Set[str]:
    """
    Reads all candidate_emotions_*.json files and returns the union as a set.
    Also populates _PENDING_CANDIDATES.
    """
    global _PENDING_CANDIDATES
    _ensure_data_dir()
    found = set()
    for name in sorted(os.listdir(DATA_DIR)):
        if name.startswith("candidate_emotions_") and name.endswith(".json"):
            path = os.path.join(DATA_DIR, name)
            try:
                data = await _read_json(path, [])
                if isinstance(data, list):
                    found.update([str(x) for x in data])
            except Exception:
                continue
    _PENDING_CANDIDATES = set(found)
    return _PENDING_CANDIDATES

async def append_candidate_label(label: str):
    """
    Append a candidate label into the current month's candidate file (if not present)
    and update in-memory set.
    """
    _ensure_data_dir()
    path = _candidate_filepath_for_now()
    try:
        existing = await _read_json(path, [])
        if label not in existing:
            existing.append(label)
            await _write_json(path, existing)
        _PENDING_CANDIDATES.add(label)
    except Exception:
        # best-effort: write initial file
        await _write_json(path, [label])
        _PENDING_CANDIDATES.add(label)

# ------------------------------------------------------------
# Merge suggestions
# ------------------------------------------------------------
async def _load_merge_suggestions() -> List[Tuple[str, str, float]]:
    raw = await _read_json(MERGE_SUGGESTIONS_PATH, [])
    # expect list of [a,b,score]
    out = []
    for item in raw:
        if isinstance(item, list) and len(item) == 3:
            out.append((str(item[0]), str(item[1]), float(item[2])))
    return out

async def _save_merge_suggestions(suggestions: Iterable[Tuple[str, str, float]]):
    await _write_json(MERGE_SUGGESTIONS_PATH, [[a,b, float(s)] for a,b,s in suggestions])

async def suggest_nearby_merges(sim_threshold: float = 0.96) -> List[Tuple[str, str, float]]:
    """
    Compute near-duplicate approved clusters and persist suggestions for human review.
    Returns list of (label_a, label_b, similarity).
    """
    async with _LOCK:
        approved = await _load_approved_embeddings()
        items = list(approved.items())
        suggestions = []
        n = len(items)
        for i in range(n):
            a_label, a_vec = items[i]
            for j in range(i+1, n):
                b_label, b_vec = items[j]
                sim = _cosine(a_vec, b_vec)
                if sim >= sim_threshold:
                    suggestions.append((a_label, b_label, float(sim)))
        await _save_merge_suggestions(suggestions)
        return suggestions

# ------------------------------------------------------------
# Public API: approve, merge, compute
# ------------------------------------------------------------
async def approve_candidate(candidate_label: str, representative_text: Optional[str] = None) -> str:
    """
    Move a candidate into the approved set by computing centroid from the
    candidate's representative text (deterministic) or by initializing with a
    small deterministic embedding derived from the text.
    Returns the approved label (may be same as candidate_label or synthesized).
    """
    async with _LOCK:
        # compute embedding for the representative text if available
        if representative_text:
            embed = await get_embedding_async(representative_text, allow_fallback=True)
            embed = np.asarray(embed, dtype=float).reshape((EMB_DIM,))
        else:
            # deterministic fallback: hash -> pseudo-vector
            h = sha256(candidate_label.encode("utf-8")).digest()
            # expand bytes deterministically to EMB_DIM floats in [-1,1]
            arr = np.frombuffer(h * ((EMB_DIM // len(h)) + 1), dtype=np.uint8)[:EMB_DIM].astype(float)
            arr = (arr - 127.5) / 127.5
            embed = arr

        # choose an approved label (synthesize from vec but allow human to rename later)
        approved_label = _synthesize_label_from_vector(embed, text_seed=candidate_label)

        # ensure cache loaded
        approved = await _load_approved_embeddings()
        # if label exists, update centroid deterministically (average)
        if approved_label in approved:
            approved_label_vec = approved[approved_label]
            new_centroid = (approved_label_vec + embed) / 2.0
            approved[approved_label] = new_centroid
        else:
            approved[approved_label] = np.asarray(embed, dtype=float)

        await _save_approved_embeddings(approved)
        # remove from pending candidates if present
        _PENDING_CANDIDATES.discard(candidate_label)
        # remove candidate_label from candidate files (best-effort)
        # (we don't delete historical files — just update current month)
        cur_path = _candidate_filepath_for_now()
        try:
            existing = await _read_json(cur_path, [])
            if candidate_label in existing:
                existing = [x for x in existing if x != candidate_label]
                await _write_json(cur_path, existing)
        except Exception:
            pass

        # After approving, recompute merge suggestions asynchronously (background-safe action)
        # We do this synchronously here but it's cheap for few approved items
        await suggest_nearby_merges()

        return approved_label

async def compute_emotion_distribution(text: str, similarity_threshold: float = 0.75) -> Dict[str, float]:
    """
    Returns a distribution over approved labels.
    If the text does not map to any approved label above threshold, create a candidate and return {}.
    Deterministic: same text -> same embedding -> same candidate label (if created).
    """
    embed = await get_embedding_async(text, allow_fallback=True)
    embed = np.asarray(embed, dtype=float).reshape((EMB_DIM,))

    async with _LOCK:
        approved = await _load_approved_embeddings()
        if approved:
            # compute cosine similarities
            labels = list(approved.keys())
            centroids = np.stack([approved[l] for l in labels], axis=1)  # EMB_DIM x n
            # efficient dot
            sims = (embed @ centroids) / ((np.linalg.norm(embed) + 1e-12) * (np.linalg.norm(centroids, axis=0) + 1e-12))
            sims = np.nan_to_num(sims, nan=0.0)
            # choose best
            best_idx = int(np.argmax(sims))
            best_sim = float(sims[best_idx])
            if best_sim >= similarity_threshold:
                chosen = labels[best_idx]
                # update centroid deterministically (moving average)
                await update_approved_embedding(chosen, embed)
                return {chosen: 1.0}

    # Not mapped: create deterministic candidate label and persist
    candidate_label = _synthesize_label_from_vector(embed, text_seed=text)
    await append_candidate_label(candidate_label)
    return {}  # empty distribution until human approves

async def update_approved_embedding(label: str, new_embed: np.ndarray):
    """
    Deterministically update an approved label centroid by averaging.
    """
    async with _LOCK:
        approved = await _load_approved_embeddings()
        if label in approved:
            approved[label] = (approved[label] + np.asarray(new_embed, dtype=float).reshape((EMB_DIM,))) / 2.0
        else:
            approved[label] = np.asarray(new_embed, dtype=float).reshape((EMB_DIM,))
        await _save_approved_embeddings(approved)

# ------------------------------------------------------------
# Helper reading functions (small API)
# ------------------------------------------------------------
def pending_candidates() -> Set[str]:
    return set(_PENDING_CANDIDATES)

async def list_approved_labels() -> List[str]:
    approved = await _load_approved_embeddings()
    return sorted(list(approved.keys()))

async def get_merge_suggestions() -> List[Tuple[str, str, float]]:
    return await _load_merge_suggestions()

async def perform_merge(label_a: str, label_b: str) -> str:
    """
    Merge label_b into label_a (human-approved). Returns resulting label (label_a).
    Centroid = average; remove label_b.
    """
    async with _LOCK:
        approved = await _load_approved_embeddings()
        if label_a not in approved or label_b not in approved:
            raise KeyError("one or both labels not approved")
        vec_a = approved[label_a]
        vec_b = approved[label_b]
        merged = (vec_a + vec_b) / 2.0
        approved[label_a] = merged
        del approved[label_b]
        await _save_approved_embeddings(approved)
        # refresh merge suggestions
        await suggest_nearby_merges()
        return label_a

# small convenience synchronous wrappers for non-async callers
def sync_load_existing_candidates() -> Set[str]:
    return asyncio.get_event_loop().run_until_complete(load_existing_candidates())

def sync_list_approved_labels() -> List[str]:
    return asyncio.get_event_loop().run_until_complete(list_approved_labels())
