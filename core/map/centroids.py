# ==========================================
# core/map/centroids.py
# save-state 202512291826 (YYYYMMDDhhmm)
# ==========================================

"""
Centroid management for embeddings (cluster-level vectors).

LOCKED INVARIANTS:

- No text → embedding conversion occurs in this module.
- All vectors are precomputed upstream.
- Missing vectors cause immediate failure.
- Journal embeddings are immutable and never rewritten.
- Deterministic IDs and month-based snapshots are preserved.
- Humans commit all structural changes.
"""

import numpy as np
from typing import Dict, List, Any, Optional
import logging
import os
import json
import asyncio
import aiofiles
from sklearn.cluster import KMeans, AgglomerativeClustering
from datetime import datetime

# ---------------- Logging ----------------
logger = logging.getLogger("peridocs.centroids")
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    logger.addHandler(h)

# ============================================================
# === CORE STATE & I/O =======================================
# ============================================================

CENTROIDS: Dict[str, np.ndarray] = {}
CENTROID_COUNTS: Dict[str, int] = {}
CENTROID_VARS: Dict[str, np.ndarray] = {}
CENTROID_DENSITIES: Dict[str, float] = {}

# Explicit snapshot history
CENTROID_HISTORY: Dict[str, List[Dict[str, Any]]] = {}

# ---------------- Paths ----------------
DATA_DIR = "data"
CENTROID_FILE_TEMPLATE = "centroids_{yearmonth}.npz"
ID_COUNTER_FILE = os.path.join(DATA_DIR, "centroid_id_counter.json")
HISTORY_FILE = os.path.join(DATA_DIR, "centroid_history.json")
JOURNALS_FILE = os.path.join(DATA_DIR, "journals.json")


# ---------------- Deterministic ID Counter ----------------
async def _load_id_counter() -> int:
    if not os.path.exists(ID_COUNTER_FILE):
        return 0
    async with aiofiles.open(ID_COUNTER_FILE, "r", encoding="utf-8") as f:
        return int(json.loads(await f.read())["next_id"])

async def _save_id_counter(val: int) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    async with aiofiles.open(ID_COUNTER_FILE, "w", encoding="utf-8") as f:
        await f.write(json.dumps({"next_id": val}, indent=2))

async def generate_id(prefix: str) -> str:
    counter = await _load_id_counter()
    new_id = f"{prefix}_{counter:08d}"
    await _save_id_counter(counter + 1)
    return new_id

# ---------------- Current NPZ Path ----------------
async def _current_centroid_file() -> str:
    yearmonth = datetime.utcnow().strftime("%Y%m")
    return os.path.join(DATA_DIR, CENTROID_FILE_TEMPLATE.format(yearmonth=yearmonth))

# ---------------- Core Persistence ----------------
async def save_state() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)

    await asyncio.to_thread(
        np.savez,
        await _current_centroid_file(),
        centroids=CENTROIDS,
        counts=CENTROID_COUNTS,
        variances=CENTROID_VARS,
        densities=CENTROID_DENSITIES,
    )

    async with aiofiles.open(HISTORY_FILE, "w", encoding="utf-8") as f:
        await f.write(json.dumps(CENTROID_HISTORY, indent=2))

    logger.info("Centroid state saved")

async def load_state() -> None:
    global CENTROIDS, CENTROID_COUNTS, CENTROID_VARS, CENTROID_DENSITIES, CENTROID_HISTORY

    path = await _current_centroid_file()
    if not os.path.exists(path):
        logger.warning("No centroid file found; starting fresh")
        return

    data = await asyncio.to_thread(np.load, path, allow_pickle=True)
    CENTROIDS = dict(data["centroids"].item())
    CENTROID_COUNTS = dict(data["counts"].item())
    CENTROID_VARS = dict(data["variances"].item())
    CENTROID_DENSITIES = dict(data["densities"].item())

    if os.path.exists(HISTORY_FILE):
        async with aiofiles.open(HISTORY_FILE, "r", encoding="utf-8") as f:
            CENTROID_HISTORY = json.loads(await f.read())
    else:
        CENTROID_HISTORY = {}

    logger.info("Centroid state loaded")

# ---------------- Snapshot Utilities ----------------
def _now_snapshot_id() -> int:
    return int(datetime.utcnow().timestamp())

def _snapshot_centroid(cid: str) -> None:
    if cid not in CENTROIDS:
        raise ValueError(f"Cannot snapshot missing centroid {cid}")
    CENTROID_HISTORY.setdefault(cid, []).append({
        "snapshot": _now_snapshot_id(),
        "vector": CENTROIDS[cid].tolist()
    })

# ============================================================
# === Math / Analysis Layer =================================
# ============================================================

def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom != 0 else 0.0

def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    return 1.0 - _cosine_similarity(a, b)

async def compute_density(centroid_vec: np.ndarray, members: List[np.ndarray]) -> float:
    if not members:
        raise RuntimeError("Density computation with zero members")
    sims = [_cosine_similarity(v, centroid_vec) for v in members]
    return float(np.mean(sims))

async def centroid_drift(cid: str) -> Optional[float]:
    history = CENTROID_HISTORY.get(cid)
    if not history or len(history) < 1:
        return None
    last_vec = np.array(history[-1]["vector"])
    return _cosine_distance(CENTROIDS[cid], last_vec)

async def cohesion_score(centroid_vec: np.ndarray, member_vecs: List[np.ndarray]) -> float:
    if not member_vecs:
        raise ValueError("Cohesion requires member vectors")
    sims = [_cosine_similarity(v, centroid_vec) for v in member_vecs]
    return float(np.var(sims))

async def hypothetical_split_analysis(member_vecs: List[np.ndarray]) -> Dict[str, Any]:
    if len(member_vecs) < 2:
        raise ValueError("Split analysis requires >=2 vectors")

    X = np.stack(member_vecs)
    centroid_before = np.mean(X, axis=0)
    cohesion_before = await cohesion_score(centroid_before, member_vecs)

    kmeans = KMeans(n_clusters=2, random_state=42).fit(X)
    results = []
    for i in (0, 1):
        cluster = X[kmeans.labels_ == i]
        cvec = np.mean(cluster, axis=0)
        results.append(await cohesion_score(cvec, cluster.tolist()))

    return {
        "cohesion_before": cohesion_before,
        "cohesion_after_avg": float(np.mean(results)),
        "explanation": (
            "This centroid decomposes into two tighter groups."
            if np.mean(results) < cohesion_before
            else "Splitting does not improve internal cohesion."
        )
    }

# ============================================================
# === Inspection / Utility ==================================
# ============================================================

async def list_centroids() -> List[Dict[str, Any]]:
    out = []
    for cid in sorted(CENTROIDS.keys()):
        out.append({
            "centroid_id": cid,
            "count": CENTROID_COUNTS[cid],
            "density": CENTROID_DENSITIES[cid],
            "avg_variance": float(np.mean(CENTROID_VARS[cid])),
        })
    return out

# ============================================================
# === Structural / Mutation Layer ===========================
# ============================================================

# ---------------- Precentroid Creation ----------------
async def create_precentroid(*, journal_entries: List[Dict[str, Any]]) -> str:
    if not journal_entries:
        raise ValueError("journal_entries required")

    vectors: List[np.ndarray] = []
    embedding_cache: Dict[str, Dict[str, List[float]]] = {}

    journal_entries = sorted(journal_entries, key=lambda e: e["journal_id"])

    for entry in journal_entries:
        jid = entry["journal_id"]
        emb_file = entry["embedding_file"]
        if not os.path.exists(emb_file):
            raise FileNotFoundError(emb_file)
        if emb_file not in embedding_cache:
            async with aiofiles.open(emb_file, "r", encoding="utf-8") as f:
                embedding_cache[emb_file] = json.loads(await f.read())
        if jid not in embedding_cache[emb_file]:
            raise KeyError(f"Missing embedding for {jid}")
        vec = embedding_cache[emb_file][jid]
        if len(vec) != 1024:
            raise ValueError(f"Embedding dim != 1024 for {jid}")
        vectors.append(np.array(vec))

    centroid_vec = np.mean(vectors, axis=0)
    cid = await generate_id("precentroid")

    CENTROIDS[cid] = centroid_vec
    CENTROID_COUNTS[cid] = len(vectors)
    CENTROID_VARS[cid] = np.var(vectors, axis=0)
    CENTROID_DENSITIES[cid] = await compute_density(centroid_vec, vectors)

    _snapshot_centroid(cid)
    await save_state()
    logger.info(f"Created precentroid {cid}")

    return cid

# ---------------- Approval ----------------
async def approve_precentroid(precentroid_id: str) -> str:
    if not precentroid_id.startswith("precentroid_"):
        raise ValueError("Only precentroids may be approved")
    if precentroid_id not in CENTROIDS:
        raise ValueError("Precentroid missing")

    new_id = precentroid_id.replace("precentroid_", "centroid_", 1)
    if new_id in CENTROIDS:
        raise RuntimeError("Centroid ID collision")

    CENTROIDS[new_id] = CENTROIDS.pop(precentroid_id)
    CENTROID_COUNTS[new_id] = CENTROID_COUNTS.pop(precentroid_id)
    CENTROID_VARS[new_id] = CENTROID_VARS.pop(precentroid_id)
    CENTROID_DENSITIES[new_id] = CENTROID_DENSITIES.pop(precentroid_id)
    CENTROID_HISTORY[new_id] = CENTROID_HISTORY.pop(precentroid_id)

    _snapshot_centroid(new_id)
    await save_state()
    logger.info(f"Approved {new_id}")

    return new_id

# ---------------- Burst / Split Commit ----------------
async def burst_rejected_precentroid(
    precentroid_id: str,
    *,
    journal_entries: List[Dict[str, Any]],
    min_similarity: float,
    n_clusters: int = 2,
) -> List[str]:
    if precentroid_id not in CENTROIDS:
        raise ValueError("Precentroid missing")

    vectors = []
    embedding_cache: Dict[str, Dict[str, List[float]]] = {}
    journal_entries = sorted(journal_entries, key=lambda e: e["journal_id"])

    for entry in journal_entries:
        jid = entry["journal_id"]
        emb_file = entry["embedding_file"]
        if emb_file not in embedding_cache:
            async with aiofiles.open(emb_file, "r", encoding="utf-8") as f:
                embedding_cache[emb_file] = json.loads(await f.read())
        vectors.append(np.array(embedding_cache[emb_file][jid]))

    X = np.stack(vectors)
    clustering = AgglomerativeClustering(
        n_clusters=min(n_clusters, len(vectors)),
        affinity="cosine",
        linkage="average",
    )
    labels = clustering.fit_predict(X)

    new_ids = []
    for lbl in sorted(set(labels)):
        idxs = np.where(labels == lbl)[0]
        cluster_vecs = X[idxs]
        centroid_vec = np.mean(cluster_vecs, axis=0)
        density = await compute_density(centroid_vec, list(cluster_vecs))
        if density < min_similarity:
            continue
        new_id = await generate_id("precentroid")
        CENTROIDS[new_id] = centroid_vec
        CENTROID_COUNTS[new_id] = len(cluster_vecs)
        CENTROID_VARS[new_id] = np.var(cluster_vecs, axis=0)
        CENTROID_DENSITIES[new_id] = density
        _snapshot_centroid(new_id)
        new_ids.append(new_id)

    for d in (CENTROIDS, CENTROID_COUNTS, CENTROID_VARS, CENTROID_DENSITIES, CENTROID_HISTORY):
        d.pop(precentroid_id, None)

    await save_state()
    logger.info(f"Burst {precentroid_id} → {new_ids}")
    return new_ids

async def commit_split(cid: str, *, member_vecs: List[np.ndarray]) -> List[str]:
    if cid not in CENTROIDS:
        raise ValueError("Centroid not found")

    X = np.stack(member_vecs)
    kmeans = KMeans(n_clusters=2, random_state=42).fit(X)
    new_ids = []
    for i in (0, 1):
        vecs = X[kmeans.labels_ == i]
        nid = await generate_id("centroid")
        CENTROIDS[nid] = np.mean(vecs, axis=0)
        CENTROID_COUNTS[nid] = len(vecs)
        CENTROID_VARS[nid] = np.var(vecs, axis=0)
        CENTROID_DENSITIES[nid] = float(np.mean([_cosine_similarity(v, CENTROIDS[nid]) for v in vecs]))
        _snapshot_centroid(nid)
        new_ids.append(nid)

    for d in (CENTROIDS, CENTROID_COUNTS, CENTROID_VARS, CENTROID_DENSITIES, CENTROID_HISTORY):
        d.pop(cid, None)

    await save_state()
    return new_ids

# ---------------- SAAJE AUTO-ASSIGN ----------------
# Software-Auto-Added Journal Entry (SAAJE)
SAAJE_AFFILIATIONS: Dict[str, Dict[str, float]] = {}  # journal_id -> {centroid_id: similarity}

async def assign_saaje(journal_entry: Dict[str, Any], min_similarity: float = 0.7) -> None:
    """
    Auto-assign a journal entry to one or more centroids if similarity >= min_similarity.
    Does not mutate centroid vectors; updates density, variance, and affiliations.
    """
    jid = journal_entry["journal_id"]
    emb_file = journal_entry["embedding_file"]

    if not os.path.exists(emb_file):
        raise FileNotFoundError(f"Embedding file not found: {emb_file}")

    async with aiofiles.open(emb_file, "r", encoding="utf-8") as f:
        embedding_data = json.loads(await f.read())

    if jid not in embedding_data:
        raise KeyError(f"Embedding missing for journal_id {jid}")

    vec = np.array(embedding_data[jid])
    if len(vec) != 1024:
        raise ValueError(f"Embedding dim != 1024 for {jid}")

    affinities: Dict[str, float] = {}

    # Compare to all existing centroids
    for cid, centroid_vec in CENTROIDS.items():
        if not cid.startswith("centroid_"):
            continue  # only approved centroids
        sim = _cosine_similarity(vec, centroid_vec)
        if sim >= min_similarity:
            affinities[cid] = sim

    if not affinities:
        logger.info(f"SAAJE {jid} did not meet min_similarity for any centroid")
        return

    # Record SAAJE affiliations
    SAAJE_AFFILIATIONS[jid] = dict(sorted(affinities.items(), key=lambda x: x[1], reverse=True))

    # Update centroid stats: density and variance
    for cid, sim in SAAJE_AFFILIATIONS[jid].items():
        # Dummy density recomputation including this SAAJE (without altering centroid_vec)
        density_members = [CENTROIDS[cid]] + [vec]  # minimal inclusion
        CENTROID_DENSITIES[cid] = float(np.mean([_cosine_similarity(v, CENTROIDS[cid]) for v in density_members]))
        CENTROID_VARS[cid] = np.var(np.vstack([CENTROIDS[cid], vec]), axis=0)

    logger.info(f"SAAJE {jid} assigned to centroids: {list(SAAJE_AFFILIATIONS[jid].keys())}")
    await save_state()
