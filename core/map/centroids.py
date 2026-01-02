# ==========================================
# core/map/centroids.py
# save-state 202601012353 (YYYYMMDDhhmm)
# ==========================================
"""
Centroid system compliant with spec 202512301012.
Maintains deterministic IDs, human approval gates, SAAJE logic, 
immutable embeddings, audit history, precentroid lifecycle, bursting,
splitting, and full async persistence. Designed for identity-stable,
state-evolving NNE management.
"""

import os
import json
import asyncio
import logging
import numpy as np
import aiofiles
import hashlib
from typing import Dict, List, Any, Optional
from datetime import datetime
from sklearn.cluster import KMeans, AgglomerativeClustering

# ---------------- Logging ----------------
logger = logging.getLogger("peridocs.centroids")
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    logger.addHandler(h)

# ---------------- Core State ----------------
CENTROIDS: Dict[str, np.ndarray] = {}
CENTROID_COUNTS: Dict[str, int] = {}
CENTROID_VARS: Dict[str, np.ndarray] = {}
CENTROID_DENSITIES: Dict[str, float] = {}
CENTROID_METADATA: Dict[str, Dict[str, Any]] = {}
CENTROID_HISTORY: Dict[str, List[Dict[str, Any]]] = {}
SAAJE_AFFILIATIONS: Dict[str, Dict[str, float]] = {} 
SAAJE_REJECTIONS: Dict[str, Dict[str, Dict[str, Any]]] = {}


# ---------------- Paths ----------------
DATA_DIR = "data"
CENTROID_FILE_TEMPLATE = "centroids_{yearmonth}.npz"
HISTORY_FILE = os.path.join(DATA_DIR, "centroid_history.json")
ID_COUNTER_FILE = os.path.join(DATA_DIR, "centroid_id_counter.json")
JOURNALS_FILE = os.path.join(DATA_DIR, "journals.json")

# ---------------- Deterministic IDs ----------------
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

# ---------------- Persistence ----------------
async def _current_centroid_file() -> str:
    yearmonth = datetime.utcnow().strftime("%Y%m")
    return os.path.join(DATA_DIR, CENTROID_FILE_TEMPLATE.format(yearmonth=yearmonth))

async def save_state() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    path = await _current_centroid_file()
    # --- ADD DIAGNOSTIC CHECK HERE ---
    def find_coroutines(obj, path="root"):
        import asyncio
        found = []
        if asyncio.iscoroutine(obj):
            found.append(path)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                found.extend(find_coroutines(v, f"{path}.{k}"))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                found.extend(find_coroutines(v, f"{path}[{i}]"))
        return found

    for name, d in [
        ("CENTROIDS", CENTROIDS),
        ("CENTROID_METADATA", CENTROID_METADATA),
        ("CENTROID_COUNTS", CENTROID_COUNTS),
        ("CENTROID_VARS", CENTROID_VARS),
        ("CENTROID_DENSITIES", CENTROID_DENSITIES),
    ]:
        coros = find_coroutines(d)
        if coros:
            print(f"[WARNING] {name} contains coroutine(s) at:", coros)
            raise RuntimeError(f"{name} contains coroutine(s) and cannot be saved")

    # --- END DIAGNOSTIC CHECK ---

    def find_bad_objects(obj, path="root"):
        import asyncio
        found = []
        if asyncio.iscoroutine(obj):
            found.append((path, "coroutine"))
        elif callable(obj):
            found.append((path, "callable"))
        elif isinstance(obj, dict):
            for k, v in obj.items():
                found.extend(find_bad_objects(v, f"{path}.{k}"))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                found.extend(find_bad_objects(v, f"{path}[{i}]"))
        return found

    for name, d in [
        ("CENTROIDS", CENTROIDS),
        ("CENTROID_METADATA", CENTROID_METADATA),
        ("CENTROID_COUNTS", CENTROID_COUNTS),
        ("CENTROID_VARS", CENTROID_VARS),
        ("CENTROID_DENSITIES", CENTROID_DENSITIES),
    ]:
        bads = find_bad_objects(d)
        if bads:
            print(f"[BAD OBJECTS] in {name}:")
            for path, typ in bads:
                print(f"  {path} → {typ}")
            raise RuntimeError(f"{name} contains unserializable objects")

        await asyncio.to_thread(np.savez, path,
                                centroids=CENTROIDS,
                                counts=CENTROID_COUNTS,
                                variances=CENTROID_VARS,
                                densities=CENTROID_DENSITIES,
                                metadata=CENTROID_METADATA,
                                saaje=SAAJE_AFFILIATIONS,
                                saaje_rejections=SAAJE_REJECTIONS,
                                )
        async with aiofiles.open(HISTORY_FILE, "w", encoding="utf-8") as f:
            await f.write(json.dumps(CENTROID_HISTORY, indent=2))
        logger.info("Centroid state saved")

async def load_state() -> None:
    global CENTROIDS, CENTROID_COUNTS, CENTROID_VARS, CENTROID_DENSITIES, CENTROID_METADATA, CENTROID_HISTORY, SAAJE_AFFILIATIONS, SAAJE_REJECTIONS
    path = await _current_centroid_file()
    if os.path.exists(path):
        data = await asyncio.to_thread(np.load, path, allow_pickle=True)
        CENTROIDS = dict(data["centroids"].item())
        CENTROID_COUNTS = dict(data["counts"].item())
        CENTROID_VARS = dict(data["variances"].item())
        CENTROID_DENSITIES = dict(data["densities"].item())
        CENTROID_METADATA = dict(data.get("metadata", {}).item())
        SAAJE_AFFILIATIONS = dict(data.get("saaje", {}).item())
        SAAJE_REJECTIONS = dict(data.get("saaje_rejections", {}).item())
    if os.path.exists(HISTORY_FILE):
        async with aiofiles.open(HISTORY_FILE, "r", encoding="utf-8") as f:
            CENTROID_HISTORY = json.loads(await f.read())
    logger.info("Centroid state loaded")

# ---------------- Snapshot ----------------
def _now_snapshot_id() -> int:
    return int(datetime.utcnow().timestamp())

def _snapshot_centroid(cid: str) -> None:
    if cid not in CENTROIDS:
        raise ValueError(f"Cannot snapshot missing centroid {cid}")
    CENTROID_HISTORY.setdefault(cid, []).append({
        "snapshot": _now_snapshot_id(),
        "vector": CENTROIDS[cid].tolist(),
        "metadata": CENTROID_METADATA.get(cid, {})
    })

# ---------------- Math / Analysis ----------------
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


# ---------------- Precentroids ----------------
from .saaje import _load_embedding_for_journal  # centralized embedding loader

# In-memory cache for batch operations
_PRECENTROID_EMB_CACHE: Dict[str, Dict[str, np.ndarray]] = {}

async def create_precentroid(*, journal_entries: List[Dict[str, Any]]) -> str:
    if not journal_entries:
        raise ValueError("journal_entries required")
    vectors: List[np.ndarray] = []

    # Sort to ensure deterministic centroid order
    journal_entries = sorted(journal_entries, key=lambda e: e["journal_id"])

    for entry in journal_entries:
        jid = entry["journal_id"]
        # Load embedding using centralized loader
        if jid not in _PRECENTROID_EMB_CACHE:
            vec = await _load_embedding_for_journal(jid)
            if vec is None:
                raise KeyError(f"Missing embedding for {jid}")
            _PRECENTROID_EMB_CACHE[jid] = vec
        else:
            vec = _PRECENTROID_EMB_CACHE[jid]

        if vec.shape[0] != 1024:
            raise ValueError(f"Embedding dim != 1024 for {jid}")
        vectors.append(vec)

    centroid_vec = np.mean(vectors, axis=0)
    cid = await cluster_id_from_entries(journal_entries)

    CENTROIDS[cid] = centroid_vec
    CENTROID_COUNTS[cid] = len(vectors)
    CENTROID_VARS[cid] = np.var(vectors, axis=0)
    CENTROID_DENSITIES[cid] = await compute_density(centroid_vec, vectors)
    CENTROID_METADATA[cid] = {"status": "pending", "label": None, "precentroid": True}

    _snapshot_centroid(cid)
    await save_state()
    logger.info(f"Created precentroid titled {cid}")
    return cid


async def approve_precentroid(precentroid_id: str) -> str:
    if not precentroid_id.startswith("precentroid_"):
        raise ValueError("Only precentroids may be approved")
    if precentroid_id not in CENTROIDS:
        raise ValueError("Precentroid missing")

    new_id = precentroid_id.replace("precentroid_", "centroid_", 1)
    if new_id in CENTROIDS:
        raise RuntimeError("Centroid ID collision")

    # Move all data from precentroid → centroid
    CENTROIDS[new_id] = CENTROIDS.pop(precentroid_id)
    CENTROID_COUNTS[new_id] = CENTROID_COUNTS.pop(precentroid_id)
    CENTROID_VARS[new_id] = CENTROID_VARS.pop(precentroid_id)
    CENTROID_DENSITIES[new_id] = CENTROID_DENSITIES.pop(precentroid_id)
    CENTROID_METADATA[new_id] = CENTROID_METADATA.pop(precentroid_id)
    CENTROID_HISTORY[new_id] = CENTROID_HISTORY.pop(precentroid_id)

    _snapshot_centroid(new_id)
    await save_state()
    logger.info(f"Approved {new_id}")
    return new_id


async def burst_rejected_precentroid(
    precentroid_id: str,
    *,
    journal_entries: List[Dict[str, Any]],
    min_similarity: float,
    n_clusters: int = 2,
) -> List[str]:
    if precentroid_id not in CENTROIDS:
        raise ValueError("Precentroid missing")

    vectors: List[np.ndarray] = []

    # Sort to ensure deterministic clustering
    journal_entries = sorted(journal_entries, key=lambda e: e["journal_id"])

    for entry in journal_entries:
        jid = entry["journal_id"]
        if jid not in _PRECENTROID_EMB_CACHE:
            vec = await _load_embedding_for_journal(jid)
            if vec is None:
                raise KeyError(f"Missing embedding for {jid}")
            _PRECENTROID_EMB_CACHE[jid] = vec
        else:
            vec = _PRECENTROID_EMB_CACHE[jid]

        vectors.append(vec)

    if not vectors:
        logger.warning(f"No embeddings to burst for {precentroid_id}")
        return []

    X = np.stack(vectors)
    clustering = AgglomerativeClustering(
        n_clusters=min(n_clusters, len(vectors)),
        affinity="cosine",
        linkage="average",
    )
    labels = clustering.fit_predict(X)

    new_ids: List[str] = []

    for lbl in sorted(set(labels)):
        idxs = np.where(labels == lbl)[0]
        cluster_vecs = X[idxs]
        centroid_vec = np.mean(cluster_vecs, axis=0)
        density = await compute_density(centroid_vec, list(cluster_vecs))
        if density < min_similarity:
            continue

        new_id = await cluster_id_from_entries(journal_entries)
        CENTROIDS[new_id] = centroid_vec
        CENTROID_COUNTS[new_id] = len(cluster_vecs)
        CENTROID_VARS[new_id] = np.var(cluster_vecs, axis=0)
        CENTROID_DENSITIES[new_id] = density
        _snapshot_centroid(new_id)
        new_ids.append(new_id)

    # Clean up rejected precentroid
    for d in (
        CENTROIDS,
        CENTROID_COUNTS,
        CENTROID_VARS,
        CENTROID_DENSITIES,
        CENTROID_METADATA,
        CENTROID_HISTORY,
    ):
        d.pop(precentroid_id, None)

    await save_state()
    logger.info(f"Burst {precentroid_id} → {new_ids}")
    return new_ids


async def commit_split(cid: str, *, member_vecs: List[np.ndarray]) -> List[str]:
    if cid not in CENTROIDS:
        raise ValueError("Centroid not found")
    if len(member_vecs) < 2:
        raise ValueError("Split requires at least 2 member vectors")

    X = np.stack(member_vecs)
    kmeans = KMeans(n_clusters=2, random_state=42).fit(X)

    new_ids: List[str] = []

    for i in (0, 1):
        vecs = X[kmeans.labels_ == i]
        nid = await generate_id("centroid")
        CENTROIDS[nid] = np.mean(vecs, axis=0)
        CENTROID_COUNTS[nid] = len(vecs)
        CENTROID_VARS[nid] = np.var(vecs, axis=0)
        CENTROID_DENSITIES[nid] = float(
            np.mean([_cosine_similarity(v, CENTROIDS[nid]) for v in vecs])
        )
        _snapshot_centroid(nid)
        new_ids.append(nid)

    # Remove original centroid
    for d in (
        CENTROIDS,
        CENTROID_COUNTS,
        CENTROID_VARS,
        CENTROID_DENSITIES,
        CENTROID_METADATA,
        CENTROID_HISTORY,
    ):
        d.pop(cid, None)

    await save_state()
    return new_ids

async def cluster_id_from_entries(entries: List[Dict]) -> str:
    """
    Deterministic precentroid ID using embeddings.
    Loads embeddings from entry['embedding'] if present,
    else from entry['embedding_file'] JSON.
    """

    if not entries:
        raise ValueError("Cannot generate precentroid ID from empty entries list")

    entries_sorted = sorted(entries, key=lambda e: e["journal_id"])
    vectors = []

    for e in entries_sorted:
        jid = e["journal_id"]
        vec = e.get("embedding")
        if vec is None:
            vec = await _load_embedding_for_journal(jid)
            if vec is None:
                raise KeyError(f"Missing embedding for {jid}")
        vectors.append(np.array(vec))

    stacked = np.stack(vectors)
    mean_vec = np.mean(stacked, axis=0)
    hash_str = hashlib.md5(mean_vec.tobytes()).hexdigest()[:8]
    return f"precentroid_{hash_str}"


# ---------------- SAAJE Assignment ----------------
async def assign_saaje(journal_entry: Dict[str, Any], min_similarity: float = 0.7) -> None:
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
    for cid, centroid_vec in CENTROIDS.items():
        if not cid.startswith("centroid_"):
            continue
        sim = _cosine_similarity(vec, centroid_vec)
        if sim >= min_similarity:
            affinities[cid] = sim
    if not affinities:
        logger.info(f"SAAJE {jid} did not meet min_similarity for any centroid")
        return
    SAAJE_AFFILIATIONS[jid] = dict(sorted(affinities.items(), key=lambda x: x[1], reverse=True))
    for cid in SAAJE_AFFILIATIONS[jid]:
        member_vecs = await get_affiliated_vectors(cid)
        if member_vecs:
            CENTROID_DENSITIES[cid] = await compute_density(CENTROIDS[cid], member_vecs)
            CENTROID_VARS[cid] = np.var(np.vstack([CENTROIDS[cid]] + member_vecs), axis=0)
    logger.info(f"SAAJE {jid} assigned to centroids: {list(SAAJE_AFFILIATIONS[jid].keys())}")
    await save_state()


# ---------------- SAAJE-Driven Vector Access ----------------
async def get_affiliated_vectors(cid: str) -> list[np.ndarray]:
    """
    Returns all journal entry vectors currently affiliated with a given centroid via SAAJE.
    """
    from .saaje import _load_embedding_for_journal  # avoid circular import

    if cid not in CENTROIDS:
        raise ValueError(f"Centroid not found: {cid}")

    vectors: list[np.ndarray] = []
    for journal_id, affinities in SAAJE_AFFILIATIONS.items():
        if cid in affinities:
            emb = await _load_embedding_for_journal(journal_id)
            if emb is not None:
                vectors.append(emb)

    return vectors


# ---------------- Split Candidate Suggestions ----------------
async def suggest_split_candidates(watch_threshold: float = 0.85) -> List[Dict[str, Any]]:
    """
    Returns a list of centroids that might benefit from splitting.
    Each entry is a dict:
        {
            "centroid_id": str,
            "drift_score": float,
            "count": int,
            "avg_variance": float
        }
    """
    out: List[Dict[str, Any]] = []
    for cid, vec in CENTROIDS.items():
        # only consider "approved" centroids
        if not cid.startswith("centroid_"):
            continue

        try:
            members = await get_affiliated_vectors(cid)
            if len(members) < 2:
                continue

            drift = await centroid_drift(cid) or 0.0
            avg_var = float(np.mean(CENTROID_VARS.get(cid, np.zeros_like(vec))))
            if drift >= watch_threshold:
                out.append({
                    "centroid_id": cid,
                    "drift_score": drift,
                    "count": len(members),
                    "avg_variance": avg_var,
                })
        except Exception as e:
            logger.warning(f"Failed to analyze centroid {cid}: {e}")
            continue
    return out


# ---------------- Utility / Inspection ----------------
async def list_centroids() -> List[Dict[str, Any]]:
    out = []
    for cid in sorted(CENTROIDS.keys()):
        out.append({
            "centroid_id": cid,
            "count": CENTROID_COUNTS.get(cid, 0),
            "density": CENTROID_DENSITIES.get(cid),
            "avg_variance": float(np.mean(CENTROID_VARS[cid])) if cid in CENTROID_VARS else None,
            "metadata": CENTROID_METADATA.get(cid),
        })
    return out

async def get_journal_entry_samples_for_centroid(
    centroid_id: str,
    *,
    limit: int = 10,
    min_similarity: float = 0.7,
    strategy: str = "top_weighted",
) -> List[Dict[str, Any]]:
    """
    Return review-safe journal entry samples affiliated with a centroid.

    This is a read-only, human-facing inspection utility.
    No mutation, no reclustering, no inference side effects.

    strategy:
        - "top_weighted": highest similarity first
        - "recent": most recent entries above threshold
        - "random": random sample above threshold
    """

    if centroid_id not in CENTROIDS:
        raise ValueError(f"Centroid not found: {centroid_id}")

    # Collect candidate affiliations
    candidates: List[Dict[str, Any]] = []

    for journal_id, affinities in SAAJE_AFFILIATIONS.items():
        sim = affinities.get(centroid_id)
        if sim is None or sim < min_similarity:
            continue

        candidates.append({
            "journal_id": journal_id,
            "similarity": float(sim),
        })

    if not candidates:
        return []

    # Strategy handling
    if strategy == "top_weighted":
        candidates.sort(key=lambda x: x["similarity"], reverse=True)

    elif strategy == "recent":
        # Requires journals.json for timestamp lookup
        if not os.path.exists(JOURNALS_FILE):
            raise FileNotFoundError("journals.json required for 'recent' strategy")

        async with aiofiles.open(JOURNALS_FILE, "r", encoding="utf-8") as f:
            journals = json.loads(await f.read())

        def _ts(jid: str) -> str:
            return journals.get(jid, {}).get("timestamp", "")

        candidates.sort(key=lambda x: _ts(x["journal_id"]), reverse=True)

    elif strategy == "random":
        import random
        random.shuffle(candidates)

    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    # Load journal content for review
    results: List[Dict[str, Any]] = []

    journal_cache: Dict[str, Dict[str, Any]] = {}
    if os.path.exists(JOURNALS_FILE):
        async with aiofiles.open(JOURNALS_FILE, "r", encoding="utf-8") as f:
            journal_cache = json.loads(await f.read())

    for item in candidates[:limit]:
        jid = item["journal_id"]
        journal = journal_cache.get(jid, {})

        results.append({
            "journal_id": jid,
            "similarity_weight": item["similarity"],
            "timestamp": journal.get("timestamp"),
            "safe_text": journal.get("safe_text", ""),
            "centroid_id": centroid_id,
        })

    return results

