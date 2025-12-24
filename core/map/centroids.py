# ==========================================
# core/map/centroids.py
# save-state 202512231649
# ==========================================

"""
Centroid management for embeddings (cluster-level vectors).

Terminology (locked for this module):

- Vector:
    A 1024-dimensional numeric array (float32/float64).
    This is the concrete numerical object used for math.

- Embedding:
    The semantic representation produced by the language model.
    In the current PeriDocs architecture, the embedding is numerically
    identical to the vector. The distinction is conceptual, not structural.

- Centroid:
    A cluster-level vector representing the running mean of multiple
    entry-level vectors, plus metadata (count, variance, density).

- Variance:
    Per-dimension spread of vectors assigned to a centroid.
    Used as a weak signal for drift and over-broad clusters.

- Precentroid:
    A proposed centroid ID for which human review is required before creation.

- Candidate Journal Entry:
    A journal entry that is unassigned or marked as "suggest_new_centroid" and
    therefore eligible for human review and precentroid formation.

Design principles:

- No silent ontology formation.
- No binary “magic thresholds” pretending to be truth.
- The system suggests; humans decide.
- Density and drift are relative, not absolute.
- Early-stage uncertainty is preserved, not collapsed.

Features:

- Tracks per-centroid mean, count, variance, and density.
- Density is relative to global average (human-scaled).
- Drift and split are flagged, never auto-executed.
- Precentroid creation is suggested, not automatic.
- Windowed persistence: centroids_YYYYMM.npz with carry-over.
- REPL-friendly inspection helpers.
"""

import numpy as np
from typing import Dict, Tuple, Optional, Any, List, Callable
import logging
import os
import json
from datetime import datetime
import random
import asyncio
import aiofiles

# ---------------- Logging Setup ----------------
logger = logging.getLogger("peridocs.centroids")
logger.setLevel(logging.INFO)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(message)s")
ch.setFormatter(formatter)

if not logger.hasHandlers():
    logger.addHandler(ch)

# ---------------- In-Memory State ----------------
CENTROIDS: Dict[str, np.ndarray] = {}
CENTROID_COUNTS: Dict[str, int] = {}
CENTROID_VARS: Dict[str, np.ndarray] = {}
CENTROID_DENSITIES: Dict[str, float] = {}

# ---------------- File Handling ----------------
CENTROID_DIR = "data"
CENTROID_FILE_TEMPLATE = "centroids_{yearmonth}.npz"

# ---------------- Global Embedding Function ----------------
_GLOBAL_EMBEDDING_FN: Optional[Callable[[str], np.ndarray]] = None

async def set_embedding_function(fn: Callable[[str], np.ndarray]):
    global _GLOBAL_EMBEDDING_FN
    _GLOBAL_EMBEDDING_FN = fn

async def get_embedding_function() -> Callable[[str], np.ndarray]:
    if _GLOBAL_EMBEDDING_FN is None:
        raise RuntimeError("Global embedding function not set. Call set_embedding_function() at startup.")
    return _GLOBAL_EMBEDDING_FN

async def current_centroid_file() -> str:
    ym = datetime.utcnow().strftime("%Y%m")
    return os.path.join(CENTROID_DIR, CENTROID_FILE_TEMPLATE.format(yearmonth=ym))

# ---------------- File I/O ----------------
async def save_centroids(file_path: Optional[str] = None):
    if file_path is None:
        file_path = await current_centroid_file()

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # Use asyncio.to_thread to avoid blocking
    await asyncio.to_thread(np.savez,
        file_path,
        centroids=CENTROIDS,
        counts=CENTROID_COUNTS,
        variances=CENTROID_VARS,
        densities=CENTROID_DENSITIES,
    )

    logger.info(f"Centroids saved to {file_path}")

async def load_centroids(file_path: Optional[str] = None):
    global CENTROIDS, CENTROID_COUNTS, CENTROID_VARS, CENTROID_DENSITIES

    if file_path is None:
        file_path = await current_centroid_file()

    if os.path.exists(file_path):
        data = await asyncio.to_thread(np.load, file_path, allow_pickle=True)
        CENTROIDS = dict(data["centroids"].item())
        CENTROID_COUNTS = dict(data["counts"].item())
        CENTROID_VARS = dict(data.get("variances", {}).item())
        CENTROID_DENSITIES = dict(data.get("densities", {}).item())
        logger.info(f"Loaded centroids from {file_path}")
        return

    # carry over previous month if present
    prev_month = (
        datetime.utcnow().replace(day=1) - np.timedelta64(1, "D")
    ).strftime("%Y%m")
    prev_file = os.path.join(CENTROID_DIR, CENTROID_FILE_TEMPLATE.format(yearmonth=prev_month))
    if os.path.exists(prev_file):
        data = await asyncio.to_thread(np.load, prev_file, allow_pickle=True)
        CENTROIDS = dict(data["centroids"].item())
        CENTROID_COUNTS = dict(data["counts"].item())
        CENTROID_VARS = dict(data.get("variances", {}).item())
        CENTROID_DENSITIES = dict(data.get("densities", {}).item())
        logger.info(f"Carried over centroids from {prev_file}")
    else:
        logger.warning("No centroid file found; starting fresh.")

# ---------------- Math Helpers ----------------
async def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom != 0 else 0.0

async def compute_density(centroid_vec: np.ndarray, member_vectors: List[np.ndarray]) -> float:
    if not member_vectors:
        return 0.0
    sims = [await cosine_similarity(v, centroid_vec) for v in member_vectors]
    return float(np.mean(sims))

async def global_average_density() -> float:
    if not CENTROID_DENSITIES:
        return 0.0
    return float(np.mean(list(CENTROID_DENSITIES.values())))

# ---------------- Inspection Helpers ----------------
async def list_centroids() -> List[Dict[str, Any]]:
    out = []
    for cid, vec in CENTROIDS.items():
        out.append({
            "centroid_id": cid,
            "count": CENTROID_COUNTS.get(cid, 0),
            "density": CENTROID_DENSITIES.get(cid),
            "avg_variance": float(np.mean(CENTROID_VARS[cid])) if cid in CENTROID_VARS else None,
            "first_10_dims": vec[:10].tolist(),
        })
    return out

async def print_centroids():
    centroids_list = await list_centroids()
    if not centroids_list:
        print("No centroids loaded.")
        return
    print(f"Total centroids: {len(centroids_list)}\n")
    for c in centroids_list:
        print(f"{c['centroid_id']} | count={c['count']} | density={c['density']} | avg_var={c['avg_variance']}")

# ---------------- Drift & Split Suggestion ----------------
async def centroid_drift_score(centroid_id: str) -> Optional[float]:
    if centroid_id not in CENTROID_DENSITIES:
        return None
    global_avg = await global_average_density()
    if global_avg == 0:
        return None
    return CENTROID_DENSITIES[centroid_id] / global_avg

async def suggest_split_candidates(watch_threshold: float = 0.85) -> List[Dict[str, Any]]:
    suggestions = []
    for cid in CENTROIDS.keys():
        score = await centroid_drift_score(cid)
        if score is not None and score < watch_threshold:
            suggestions.append({
                "centroid_id": cid,
                "drift_score": round(score, 3),
                "count": CENTROID_COUNTS.get(cid, 0),
                "avg_variance": float(np.mean(CENTROID_VARS.get(cid, 0))),
            })
    return suggestions

async def print_split_suggestions():
    suggestions = await suggest_split_candidates()
    if not suggestions:
        print("No centroid split suggestions.")
        return
    print("Centroid split suggestions:")
    for s in suggestions:
        print(f"- {s['centroid_id']} | drift={s['drift_score']} | count={s['count']} | avg_var={s['avg_variance']}")

# ---------------- Manual Split Execution ----------------
async def split_centroid_with_vectors(centroid_id: str, member_vectors: List[np.ndarray]) -> List[str]:
    from sklearn.cluster import KMeans
    if len(member_vectors) < 2:
        return [centroid_id]
    X = np.stack(member_vectors)
    kmeans = await asyncio.to_thread(KMeans(n_clusters=2, random_state=42).fit, X)
    new_ids = []
    for i in range(2):
        new_vec = kmeans.cluster_centers_[i]
        new_id = f"{centroid_id}_split{i}"
        CENTROIDS[new_id] = new_vec
        idxs = np.where(kmeans.labels_ == i)[0]
        CENTROID_COUNTS[new_id] = len(idxs)
        CENTROID_VARS[new_id] = np.var(X[idxs], axis=0)
        CENTROID_DENSITIES[new_id] = float(np.mean([await cosine_similarity(v, new_vec) for v in X[idxs]]))
        new_ids.append(new_id)
    # Remove old centroid
    CENTROIDS.pop(centroid_id, None)
    CENTROID_COUNTS.pop(centroid_id, None)
    CENTROID_VARS.pop(centroid_id, None)
    CENTROID_DENSITIES.pop(centroid_id, None)
    logger.info(f"Split centroid {centroid_id} into {new_ids}")
    await save_centroids()
    return new_ids

# ---------------- Main Assignment Logic ----------------
async def assign_vector_to_existing_centroids(vec: np.ndarray, similarity_threshold: float = 0.78, semantic_score: Optional[float] = None, journal_entry: Optional[dict] = None) -> Tuple[str, float]:
    if not CENTROIDS:
        label = "suggest_new_centroid"
        score = float(semantic_score) if semantic_score is not None else 0.0
        if journal_entry is not None:
            journal_entry.setdefault("nlp", {})["assigned_centroid_id"] = label
        return label, score
    best_id = None
    best_sim = -1.0
    for cid, centroid_vec in CENTROIDS.items():
        sim = await cosine_similarity(vec, centroid_vec)
        if sim > best_sim:
            best_sim = sim
            best_id = cid
    if best_sim >= similarity_threshold and best_id is not None:
        count = CENTROID_COUNTS[best_id]
        old_mean = CENTROIDS[best_id]
        new_mean = (old_mean * count + vec) / (count + 1)
        old_var = CENTROID_VARS.get(best_id, np.zeros_like(vec))
        new_var = (old_var * count + (vec - old_mean) ** 2) / (count + 1)
        CENTROIDS[best_id] = new_mean
        CENTROID_COUNTS[best_id] = count + 1
        CENTROID_VARS[best_id] = new_var
        CENTROID_DENSITIES[best_id] = (CENTROID_DENSITIES.get(best_id, best_sim) * count + best_sim) / (count + 1)
        if journal_entry is not None:
            journal_entry.setdefault("nlp", {})["assigned_centroid_id"] = best_id
        await save_centroids()
        return best_id, 1.0 - best_sim
    label = "suggest_new_centroid"
    if journal_entry is not None:
        journal_entry.setdefault("nlp", {})["assigned_centroid_id"] = label
    return label, float(semantic_score) if semantic_score is not None else 1.0 - best_sim

# ---------------- Candidate / Precentroid Logic ----------------
async def load_candidate_journal_entries_for_precentroid(precentroid_id: str) -> List[str]:
    JOURNALS_FILE = os.path.join(CENTROID_DIR, "journals.json")
    if not os.path.exists(JOURNALS_FILE):
        return []
    try:
        async with aiofiles.open(JOURNALS_FILE, "r", encoding="utf-8") as f:
            content = await f.read()
            all_entries = json.loads(content)
    except Exception as e:
        logger.warning(f"Failed to load journals.json: {e}")
        return []
    candidate_entries = []
    for entry in all_entries:
        assigned_id = entry.get("nlp", {}).get("assigned_centroid_id")
        if assigned_id is None or assigned_id == "suggest_new_centroid":
            candidate_entries.append(entry.get("safe_text", ""))
    return candidate_entries

async def create_centroid_from_precentroid(precentroid_id: str):
    candidate_entries = await load_candidate_journal_entries_for_precentroid(precentroid_id)
    if not candidate_entries:
        logger.warning(f"No candidate entries found for precentroid {precentroid_id}")
        return
    embedding_fn = await get_embedding_function()
    candidate_vectors = [await embedding_fn(text) for text in candidate_entries]
    centroid_vec = np.mean(candidate_vectors, axis=0)
    CENTROIDS[precentroid_id] = centroid_vec
    CENTROID_COUNTS[precentroid_id] = len(candidate_vectors)
    CENTROID_VARS[precentroid_id] = np.var(np.stack(candidate_vectors), axis=0)
    CENTROID_DENSITIES[precentroid_id] = await compute_density(centroid_vec, candidate_vectors)
    await save_centroids()
    logger.info(f"Created centroid {precentroid_id} from {len(candidate_vectors)} candidate entries.")

async def get_journal_entry_samples_for_centroid(centroid_id: str) -> List[str]:
    JOURNALS_FILE = os.path.join(CENTROID_DIR, "journals.json")
    if not os.path.exists(JOURNALS_FILE):
        return []
    try:
        async with aiofiles.open(JOURNALS_FILE, "r", encoding="utf-8") as f:
            content = await f.read()
            all_entries = json.loads(content)
    except Exception as e:
        logger.warning(f"Failed to load journals.json: {e}")
        return []
    samples = []
    for entry in all_entries:
        assigned_id = entry.get("nlp", {}).get("assigned_centroid_id")
        if assigned_id == centroid_id or (centroid_id.startswith("precentroid_") and (assigned_id is None or assigned_id == "suggest_new_centroid")):
            text = entry.get("safe_text", "")
            if text:
                samples.append(text)
    return samples
