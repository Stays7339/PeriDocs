# ==========================================
# core/map/centroids.py
# save-state 202512271141
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
import asyncio
import aiofiles
import glob

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

# ---------------- Helper: Load precomputed embeddings ----------------
async def load_embeddings_from_dumps(entry_texts: List[str]) -> List[np.ndarray]:
    dump_pattern = os.path.join(CENTROID_DIR, "journals_embeddings_dump*.npz")
    dump_files = sorted(glob.glob(dump_pattern))
    embedding_map: Dict[str, np.ndarray] = {}

    for dump_file in dump_files:
        try:
            data = np.load(dump_file, allow_pickle=True)
            dump_dict = dict(data.get("embeddings", {}).item())
            embedding_map.update(dump_dict)
        except Exception as e:
            logger.warning(f"Failed to load embeddings from {dump_file}: {e}")

    vectors = []
    for text in entry_texts:
        vec = embedding_map.get(text)
        if vec is None:
            vec = np.zeros(1024, dtype=np.float32)
        vectors.append(vec)

    return vectors

# ---------------- File I/O ----------------
async def save_centroids(file_path: Optional[str] = None):
    if file_path is None:
        file_path = await current_centroid_file()

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

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
        new_id = datetime.utcnow().strftime("centroid_%Y%m%d%H%M%S")  # timestamped ID
        CENTROIDS[new_id] = new_vec
        idxs = np.where(kmeans.labels_ == i)[0]
        CENTROID_COUNTS[new_id] = len(idxs)
        CENTROID_VARS[new_id] = np.var(X[idxs], axis=0)
        CENTROID_DENSITIES[new_id] = float(np.mean([await cosine_similarity(v, new_vec) for v in X[idxs]]))
        new_ids.append(new_id)
    CENTROIDS.pop(centroid_id, None)
    CENTROID_COUNTS.pop(centroid_id, None)
    CENTROID_VARS.pop(centroid_id, None)
    CENTROID_DENSITIES.pop(centroid_id, None)
    logger.info(f"Split centroid {centroid_id} into {new_ids}")
    await save_centroids()
    return new_ids

def _generate_timestamped_id(prefix: str = "precentroid") -> str:
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"{prefix}_{ts}"

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

async def create_precentroid_or_centroid(
    entries: Optional[List[Dict]] = None,
    precentroid_id: Optional[str] = None,
    promote: bool = False
) -> str:
    """
    Create a precentroid or a centroid from either:
      - A list of entries, or
      - An existing precentroid ID (loads candidate entries from journals.json)

    If promote=True, creates a permanent centroid instead of a precentroid.
    Returns the timestamped ID of the created object.
    """
    if entries is None:
        if precentroid_id is None:
            raise ValueError("Must provide either entries or precentroid_id")
        entries_texts = await load_candidate_journal_entries_for_precentroid(precentroid_id)
        if not entries_texts:
            logger.warning(f"No candidate entries found for precentroid {precentroid_id}")
            return precentroid_id
        vectors = await load_embeddings_from_dumps(entries_texts)
        entries = [{"embedding": vec} for vec in vectors]
        centroid_vec = np.mean(vectors, axis=0)
    else:
        vectors = [e["embedding"] for e in entries]
        centroid_vec = np.mean(vectors, axis=0)

    prefix = "centroid" if promote else "precentroid"
    ts_id = _generate_timestamped_id(prefix=prefix)

    CENTROIDS[ts_id] = centroid_vec
    CENTROID_COUNTS[ts_id] = len(vectors)
    CENTROID_VARS[ts_id] = np.var(vectors, axis=0)
    CENTROID_DENSITIES[ts_id] = await compute_density(centroid_vec, vectors)

    await save_centroids()
    logger.info(f"Created {'centroid' if promote else 'precentroid'} {ts_id} from {len(entries)} entries")
    return ts_id

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

# ---------------- Batch Update Centroid Densities ----------------
async def recalc_all_centroid_densities():
    """
    Recalculate densities for all loaded centroids based on their current member vectors.
    Uses get_journal_entry_samples_for_centroid to fetch texts and the global embedding function.
    """
    embedding_fn = await get_embedding_function()
    for cid in list(CENTROIDS.keys()):
        try:
            samples = await get_journal_entry_samples_for_centroid(cid)
            if not samples:
                CENTROID_DENSITIES[cid] = 0.0
                continue
            vectors = [await embedding_fn(text) for text in samples]
            centroid_vec = CENTROIDS[cid]
            CENTROID_DENSITIES[cid] = await compute_density(centroid_vec, vectors)
        except Exception as e:
            logger.warning(f"Failed to recalc density for centroid {cid}: {e}")
    await save_centroids()
    logger.info("Recalculated densities for all centroids.")

# ================= Lineage + Backup Extension =================

# ---------------- In-Memory Lineage State ----------------
CENTROID_PARENTS: Dict[str, Optional[str]] = {}
CENTROID_METADATA: Dict[str, Dict[str, Any]] = {}

# ---------------- Backup Helpers ----------------
def _backup_root_dir() -> str:
    return os.path.join(CENTROID_DIR, "backup")

def _timestamp() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")

async def _write_backup_snapshot(payload: Dict[str, Any]) -> None:
    ts = _timestamp()
    backup_dir = os.path.join(_backup_root_dir(), ts)
    os.makedirs(backup_dir, exist_ok=True)

    backup_file = os.path.join(
        backup_dir,
        f"centroid_backup_{ts}.json"
    )

    async with aiofiles.open(backup_file, "w", encoding="utf-8") as f:
        await f.write(json.dumps(payload, indent=2, default=str))

    logger.info(f"Centroid lineage backup written to {backup_file}")

# ---------------- Promotion with Explicit Parent ----------------
async def promote_precentroid_to_centroid(
    precentroid_id: str,
    entries: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Promote an existing precentroid into a new centroid.

    - Creates a NEW centroid ID
    - Records parent_centroid_id explicitly
    - Stores original precentroid ID as immutable metadata
    - Writes a timestamped backup snapshot
    """

    if precentroid_id not in CENTROIDS:
        raise ValueError(f"Precentroid {precentroid_id} does not exist")

    # derive vectors
    if entries is not None:
        vectors = [e["embedding"] for e in entries]
    else:
        samples = await get_journal_entry_samples_for_centroid(precentroid_id)
        if not samples:
            raise ValueError(f"No samples found for precentroid {precentroid_id}")
        embedding_fn = await get_embedding_function()
        vectors = [await embedding_fn(text) for text in samples]

    centroid_vec = np.mean(vectors, axis=0)

    new_id = _generate_timestamped_id(prefix="centroid")

    # create new centroid
    CENTROIDS[new_id] = centroid_vec
    CENTROID_COUNTS[new_id] = len(vectors)
    CENTROID_VARS[new_id] = np.var(vectors, axis=0)
    CENTROID_DENSITIES[new_id] = await compute_density(centroid_vec, vectors)

    # lineage
    CENTROID_PARENTS[new_id] = precentroid_id
    CENTROID_METADATA[new_id] = {
        "created_at": datetime.utcnow().isoformat(),
        "parent_centroid_id": precentroid_id,
        "source_type": "promotion",
    }

    # snapshot backup
    await _write_backup_snapshot({
        "event": "promote_precentroid",
        "timestamp": datetime.utcnow().isoformat(),
        "precentroid_id": precentroid_id,
        "new_centroid_id": new_id,
        "counts": CENTROID_COUNTS[new_id],
        "density": CENTROID_DENSITIES[new_id],
        "metadata": CENTROID_METADATA[new_id],
    })

    await save_centroids()
    logger.info(f"Promoted {precentroid_id} → {new_id}")

    return new_id

# ---------------- Lineage Inspection ----------------
async def get_centroid_lineage(centroid_id: str) -> Dict[str, Any]:
    return {
        "centroid_id": centroid_id,
        "parent_centroid_id": CENTROID_PARENTS.get(centroid_id),
        "metadata": CENTROID_METADATA.get(centroid_id, {}),
    }

# ================= Precentroid Confirmation & Cleanup =================
# explicit, human-acknowledged deletion only

async def confirm_centroid_operational(
    centroid_id: str,
    *,
    require_parent: bool = True
) -> None:
    """
    Explicitly confirm that a promoted centroid is operating correctly.

    Only after this confirmation:
      - the parent precentroid (if any) is deleted
      - deletion is backed up with full metadata

    This function is intentionally irreversible.
    """

    if centroid_id not in CENTROIDS:
        raise ValueError(f"Centroid {centroid_id} does not exist")

    parent_id = CENTROID_PARENTS.get(centroid_id)

    if require_parent and not parent_id:
        raise ValueError(f"Centroid {centroid_id} has no parent precentroid")

    if parent_id and parent_id not in CENTROIDS:
        raise ValueError(f"Parent precentroid {parent_id} not found")

    # mark confirmed
    CENTROID_METADATA.setdefault(centroid_id, {})
    CENTROID_METADATA[centroid_id]["confirmed_at"] = datetime.utcnow().isoformat()
    CENTROID_METADATA[centroid_id]["status"] = "confirmed"

    # backup snapshot BEFORE deletion
    await _write_backup_snapshot({
        "event": "confirm_centroid_and_delete_precentroid",
        "timestamp": datetime.utcnow().isoformat(),
        "centroid_id": centroid_id,
        "deleted_precentroid_id": parent_id,
        "centroid_metadata": CENTROID_METADATA.get(centroid_id),
        "precentroid_state": {
            "vector": CENTROIDS.get(parent_id).tolist() if parent_id else None,
            "count": CENTROID_COUNTS.get(parent_id),
            "density": CENTROID_DENSITIES.get(parent_id),
        },
    })

    # delete precentroid safely
    if parent_id:
        CENTROIDS.pop(parent_id, None)
        CENTROID_COUNTS.pop(parent_id, None)
        CENTROID_VARS.pop(parent_id, None)
        CENTROID_DENSITIES.pop(parent_id, None)
        CENTROID_METADATA.pop(parent_id, None)
        CENTROID_PARENTS.pop(parent_id, None)

        logger.info(f"Precentroid {parent_id} deleted after confirmation of {centroid_id}")

    await save_centroids()
