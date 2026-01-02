# ==========================================
# core/map/centroids.py
# redraft 202601021714
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
from core.map import ledger

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
CENTROID_FILE_TEMPLATE = "centroids.npz"
HISTORY_FILE = os.path.join(DATA_DIR, "centroid_history.json")
JOURNALS_FILE = os.path.join(DATA_DIR, "journals.json")

# ---------------- Utilities ----------------
def _proposal_fingerprint(*, journal_ids: list[str], similarity_threshold: float) -> str:
    h = hashlib.sha256()
    for jid in sorted(journal_ids):
        h.update(jid.encode("utf-8"))
        h.update(b"\0")
    h.update(str(similarity_threshold).encode("utf-8"))
    return h.hexdigest()

def _burst_proposal_fingerprint(parent_id: str, member_journal_ids: list[str]) -> str:
    h = hashlib.sha256()
    h.update(parent_id.encode())
    h.update(b"\0")
    for jid in sorted(member_journal_ids):
        h.update(jid.encode())
        h.update(b"\0")
    return h.hexdigest()

def _check_serializable(obj, path="root"):
    """Recursively check for unserializable objects or coroutines."""
    import asyncio
    found = []
    if asyncio.iscoroutine(obj):
        found.append((path, "coroutine"))
    elif callable(obj):
        found.append((path, "callable"))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            found.extend(_check_serializable(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(_check_serializable(v, f"{path}[{i}]"))
    return found

def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom != 0 else 0.0

def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    return 1.0 - _cosine_similarity(a, b)


def _next_snapshot_index(cid: str) -> int:
    """
    Deterministic, replay-safe snapshot index.
    Snapshot order is derived solely from centroid-local history length.
    """
    return len(CENTROID_HISTORY.get(cid, []))


def _canonical_fingerprint_payload(*, journal_ids: list[str], embeddings: list[np.ndarray], code_version: str) -> bytes:
    h = hashlib.sha256()
    h.update(code_version.encode("utf-8"))
    h.update(b"\0")
    for jid, vec in zip(journal_ids, embeddings):
        h.update(jid.encode("utf-8"))
        h.update(b"\0")
        h.update(vec.astype(np.float32).tobytes())
        h.update(b"\0")
    return h.digest()

# ---------------- Persistence ----------------
async def _current_centroid_file() -> str:
    return os.path.join(DATA_DIR, CENTROID_FILE_TEMPLATE)

async def save_state() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    path = await _current_centroid_file()

    # --- check serializable ---
    for name, d in [
        ("CENTROIDS", CENTROIDS),
        ("CENTROID_METADATA", CENTROID_METADATA),
        ("CENTROID_COUNTS", CENTROID_COUNTS),
        ("CENTROID_VARS", CENTROID_VARS),
        ("CENTROID_DENSITIES", CENTROID_DENSITIES),
    ]:
        bads = _check_serializable(d)
        if bads:
            print(f"[BAD OBJECTS] in {name}:")
            for path_, typ in bads:
                print(f"  {path_} → {typ}")
            raise RuntimeError(f"{name} contains unserializable objects")

    await asyncio.to_thread(np.savez, path,
                            centroids=CENTROIDS,
                            counts=CENTROID_COUNTS,
                            variances=CENTROID_VARS,
                            densities=CENTROID_DENSITIES,
                            metadata=CENTROID_METADATA,
                            saaje=SAAJE_AFFILIATIONS,
                            saaje_rejections=SAAJE_REJECTIONS)
    async with aiofiles.open(HISTORY_FILE, "w", encoding="utf-8") as f:
        await f.write(json.dumps(CENTROID_HISTORY, indent=2))
    logger.info("Centroid state saved")

    from core.map import ledger as ledger_mod

    ledger_state = ledger_mod._load_ledger()
    ledger_state["corpus_fingerprint"] = _compute_expected_corpus_fingerprint()
    ledger_mod._save_ledger(ledger_state)


async def load_state() -> None:
    global CENTROIDS, CENTROID_COUNTS, CENTROID_VARS, CENTROID_DENSITIES
    global CENTROID_METADATA, CENTROID_HISTORY, SAAJE_AFFILIATIONS, SAAJE_REJECTIONS

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
    # after loading CENTROIDS, etc
    ledger = ledger._load_ledger()
    if ledger.get("corpus_fingerprint") is not None:
        fingerprint_actual = ledger["corpus_fingerprint"]
        fingerprint_expected = ledger.get("corpus_fingerprint")  # recompute if needed
        assert_corpus_fingerprint(fingerprint_expected, fingerprint_actual)
    
    ledger_state = ledger._load_ledger()
    expected = ledger_state.get("corpus_fingerprint")

    if expected:
        actual = _compute_expected_corpus_fingerprint()
        ledger.assert_corpus_fingerprint(expected, actual)



# ---------------- Embedding Loader ----------------
_PRECENTROID_EMB_CACHE: Dict[str, np.ndarray] = {}

async def _load_embedding_for_journal(jid: str) -> np.ndarray:
    """
    Standalone embedding loader.
    Expects journals.json to have 'embedding' dict keyed by journal_id.
    """
    if jid in _PRECENTROID_EMB_CACHE:
        return _PRECENTROID_EMB_CACHE[jid]

    if not os.path.exists(JOURNALS_FILE):
        raise FileNotFoundError("journals.json missing")

    async with aiofiles.open(JOURNALS_FILE, "r", encoding="utf-8") as f:
        journals = json.loads(await f.read())

    embedding = journals.get(jid, {}).get("embedding")
    if embedding is None:
        raise KeyError(f"No embedding for journal_id {jid}")

    vec = np.array(embedding)
    if vec.shape[0] != 1024:
        raise ValueError(f"Embedding dim != 1024 for {jid}")

    _PRECENTROID_EMB_CACHE[jid] = vec
    return vec

# ---------------- Precentroid Lifecycle ----------------
async def allocate_precentroid_id(
    *,
    journal_ids: list[str],
    similarity_threshold: float,
) -> str:
    proposal_fp = ledger.compute_proposal_fingerprint(
        journal_ids=journal_ids,
        similarity_threshold=similarity_threshold,
    )

    numeric_id = ledger.allocate_id_for_proposal(
        proposal_fingerprint=proposal_fp,
        proposal_payload={
            "journal_ids": journal_ids,
            "similarity_threshold": similarity_threshold,
        },
    )

    return f"precentroid_{numeric_id:011d}"


async def create_precentroid(
    *,
    journal_entries: List[Dict[str, Any]],
    similarity_threshold: float = 0.95,
) -> str:
    if not journal_entries:
        raise ValueError("journal_entries required")

    journal_entries = sorted(journal_entries, key=lambda e: e["journal_id"])
    journal_ids = [e["journal_id"] for e in journal_entries]

    vectors = [await _load_embedding_for_journal(jid) for jid in journal_ids]
    centroid_vec = np.mean(vectors, axis=0)

    cid = await allocate_precentroid_id(
        journal_ids=journal_ids,
        similarity_threshold=similarity_threshold,
    )

    CENTROIDS[cid] = centroid_vec
    CENTROID_COUNTS[cid] = len(vectors)
    CENTROID_VARS[cid] = np.var(vectors, axis=0)
    CENTROID_DENSITIES[cid] = float(
        np.mean([_cosine_similarity(v, centroid_vec) for v in vectors])
    )
    CENTROID_METADATA[cid] = {
        "status": "pending",
        "label": None,
        "precentroid": True,
    }
    CENTROID_HISTORY[cid] = []

    _snapshot_centroid(cid)
    await save_state()
    logger.info(f"Created precentroid {cid}")
    return cid


# ---------------- Snapshots ----------------
def _snapshot_centroid(cid: str) -> None:
    """
    Snapshot the current state of a centroid.
    Stores:
      - Quantized vector fingerprint
      - Metadata
      - Affiliated journal IDs at snapshot time
    """
    if cid not in CENTROIDS:
        raise ValueError(f"Cannot snapshot missing centroid {cid}")

    snapshot_index = _next_snapshot_index(cid)

    # Capture affiliated journal IDs at this moment
    affiliated_journal_ids = sorted(
        jid for jid, affs in SAAJE_AFFILIATIONS.items() if cid in affs
    )

    # Build the snapshot
    snapshot_data = {
        "snapshot_index": snapshot_index,
        "vector": CENTROIDS[cid].tolist(),
        "metadata": CENTROID_METADATA.get(cid, {}),
        "affiliated_journal_ids": affiliated_journal_ids,
        "fingerprint": compute_centroid_fingerprint_sync(cid),
    }

    CENTROID_HISTORY.setdefault(cid, []).append(snapshot_data)

# ---------------- Density / Cohesion / Drift ----------------
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

# ---------------- Precentroid → Centroid ----------------
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

# ---------------- Bursting / Splitting ----------------
async def burst_rejected_precentroid(
    precentroid_id: str,
    *,
    journal_entries: list[dict[str, Any]],
    min_similarity: float,
    n_clusters: int = 2,
) -> list[str]:
    if precentroid_id not in CENTROIDS:
        raise ValueError("Precentroid missing")

    journal_entries = sorted(journal_entries, key=lambda e: e["journal_id"])
    vectors = [await _load_embedding_for_journal(e["journal_id"]) for e in journal_entries]

    if not vectors:
        logger.warning(f"No embeddings to burst for {precentroid_id}")
        return []

    if len(vectors) == 1:
        # Only one vector → no burst needed
        return []

    X = np.stack(vectors)
    clustering = AgglomerativeClustering(
        n_clusters=min(n_clusters, len(vectors)),
        metric="cosine",
        linkage="average",
    )
    labels = clustering.fit_predict(X)
    new_ids: list[str] = []

    for lbl in sorted(set(labels)):
        idxs = np.where(labels == lbl)[0]
        cluster_vecs = X[idxs]
        centroid_vec = np.mean(cluster_vecs, axis=0)
        density = await compute_density(centroid_vec, list(cluster_vecs))

        if density < min_similarity:
            continue

        cluster_jids = [journal_entries[i]["journal_id"] for i in idxs]
        proposal_fp = _burst_proposal_fingerprint(parent_id=precentroid_id, member_journal_ids=cluster_jids)

        # Assign deterministic incremental ID via ledger
        new_id_num = await ledger.allocate_id_if_absent(
            proposal_fingerprint=proposal_fp,
            proposal_payload={"journal_ids": cluster_jids, "parent": precentroid_id},
        )
        new_id = f"precentroid_{new_id_num:011d}"

        # Assign all centroid properties
        CENTROIDS[new_id] = centroid_vec
        CENTROID_COUNTS[new_id] = len(cluster_vecs)
        CENTROID_VARS[new_id] = np.var(cluster_vecs, axis=0)
        CENTROID_DENSITIES[new_id] = density
        CENTROID_METADATA[new_id] = {"status": "pending", "precentroid": True}

        await _snapshot_centroid(new_id)
        new_ids.append(new_id)

    # Clean up rejected precentroid
    for d in (CENTROIDS, CENTROID_COUNTS, CENTROID_VARS, CENTROID_DENSITIES, CENTROID_METADATA, CENTROID_HISTORY):
        d.pop(precentroid_id, None)

    await save_state()
    logger.info(f"Burst {precentroid_id} → {new_ids}")
    return new_ids

async def commit_split(cid: str, *, member_vecs: list[np.ndarray]) -> list[str]:
    """
    Split a centroid into two precentroids using KMeans.
    Returns list of new precentroid IDs.
    """
    if cid not in CENTROIDS:
        raise ValueError("Centroid not found")
    if len(member_vecs) < 2:
        raise ValueError("Split requires at least 2 member vectors")

    X = np.stack(member_vecs)
    kmeans = KMeans(n_clusters=2, random_state=42).fit(X)
    new_ids: list[str] = []

    for i in (0, 1):
        vecs = X[kmeans.labels_ == i]

        # Compute deterministic fingerprint
        fingerprint = hashlib.sha256(np.vstack(vecs).tobytes()).hexdigest()

        # Allocate a deterministic ID (async)
        nid_num = await ledger.allocate_id_if_absent(
            proposal_fingerprint=fingerprint,
            proposal_payload={"member_count": len(vecs), "parent": cid},
        )
        nid = f"precentroid_{nid_num:011d}"

        # Assign all centroid properties AFTER nid is defined
        CENTROIDS[nid] = np.mean(vecs, axis=0)
        CENTROID_COUNTS[nid] = len(vecs)
        CENTROID_VARS[nid] = np.var(vecs, axis=0)
        CENTROID_DENSITIES[nid] = float(np.mean([_cosine_similarity(v, CENTROIDS[nid]) for v in vecs]))
        CENTROID_METADATA[nid] = {"status": "pending", "precentroid": True}

        await _snapshot_centroid(nid)
        new_ids.append(nid)

    # Remove original centroid and all associated metadata
    for d in (CENTROIDS, CENTROID_COUNTS, CENTROID_VARS, CENTROID_DENSITIES, CENTROID_METADATA, CENTROID_HISTORY):
        d.pop(cid, None)

    await save_state()
    return new_ids

# ---------------- SAAJE Assignment / Affiliated Access ----------------
async def assign_saaje(journal_entry: Dict[str, Any], min_similarity: float = 0.7) -> None:
    jid = journal_entry["journal_id"]
    vec = await _load_embedding_for_journal(jid)
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

    # Recompute centroid stats
    for cid in SAAJE_AFFILIATIONS[jid]:
        member_vecs = await get_affiliated_vectors(cid)
        if member_vecs:
            CENTROID_DENSITIES[cid] = await compute_density(CENTROIDS[cid], member_vecs)
            CENTROID_VARS[cid] = np.var(np.vstack([CENTROIDS[cid]] + member_vecs), axis=0)
    logger.info(f"SAAJE {jid} assigned to centroids: {list(SAAJE_AFFILIATIONS[jid].keys())}")
    await save_state()

async def get_affiliated_vectors(cid: str) -> list[np.ndarray]:
    if cid not in CENTROIDS:
        raise ValueError(f"Centroid not found: {cid}")

    vectors: list[np.ndarray] = []
    for journal_id, affinities in SAAJE_AFFILIATIONS.items():
        if cid in affinities:
            emb = await _load_embedding_for_journal(journal_id)
            vectors.append(emb)
    return vectors

# ---------------- Split Candidate Suggestions ----------------
async def suggest_split_candidates(watch_threshold: float = 0.85) -> list[dict]:
    tasks = [_analyze_centroid_for_split(cid, watch_threshold) for cid in CENTROIDS if cid.startswith("centroid_")]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r]

async def _analyze_centroid_for_split(cid: str, watch_threshold: float) -> Optional[dict]:
    try:
        members = await get_affiliated_vectors(cid)
        if len(members) < 2:
            return None
        drift = await centroid_drift(cid) or 0.0
        avg_var = float(np.mean(CENTROID_VARS.get(cid, np.zeros_like(CENTROIDS[cid]))))
        if drift >= watch_threshold:
            return {"centroid_id": cid, "drift_score": drift, "count": len(members), "avg_variance": avg_var}
    except Exception as e:
        logger.warning(f"Failed to analyze centroid {cid}: {e}")
        return None

# ---------------- Inspection Utilities ----------------
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
    if centroid_id not in CENTROIDS:
        raise ValueError(f"Centroid not found: {centroid_id}")

    candidates: List[Dict[str, Any]] = []
    for journal_id, affinities in SAAJE_AFFILIATIONS.items():
        sim = affinities.get(centroid_id)
        if sim is not None and sim >= min_similarity:
            candidates.append({"journal_id": journal_id, "similarity": float(sim)})

    if not candidates:
        return []

    # Strategy handling
    if strategy == "top_weighted":
        candidates.sort(key=lambda x: x["similarity"], reverse=True)
    elif strategy == "recent":
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

    # Load journal content
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

# ---------------- Centroid Fingerprints ----------------
async def compute_centroid_fingerprint(cid: str) -> str:
    vec = CENTROIDS[cid]
    h = hashlib.sha256()
    qvec = _quantize(vec)  # <-- quantize before hashing
    h.update(qvec.tobytes())
    return "sha256:" + h.hexdigest()

def compute_centroid_fingerprint_sync(cid: str) -> str:
    """
    Synchronous wrapper for deterministic contexts
    (snapshots, persistence, replay).
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(compute_centroid_fingerprint(cid))
    finally:
        loop.close()


def _quantize(vec: np.ndarray, precision: int = 6) -> np.ndarray:
    """
    Convert a float vector into deterministic integers for hashing.
    """
    scale = 10 ** precision
    return (vec * scale).round().astype(np.int64)
