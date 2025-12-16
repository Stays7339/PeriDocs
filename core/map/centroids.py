# ==========================================
# core/map/centroids.py
# save-state updated 202512161750
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
- First-centroid creation is suggested, not automatic.
- Windowed persistence: centroids_YYYYMM.npz with carry-over.
- REPL-friendly inspection helpers.
"""

import numpy as np
from typing import Dict, Tuple, Optional, Any, List
import logging
import os
from datetime import datetime

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


def current_centroid_file() -> str:
    ym = datetime.utcnow().strftime("%Y%m")
    return os.path.join(
        CENTROID_DIR,
        CENTROID_FILE_TEMPLATE.format(yearmonth=ym)
    )


def save_centroids(file_path: Optional[str] = None):
    if file_path is None:
        file_path = current_centroid_file()

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    np.savez(
        file_path,
        centroids=CENTROIDS,
        counts=CENTROID_COUNTS,
        variances=CENTROID_VARS,
        densities=CENTROID_DENSITIES,
    )

    logger.info(f"Centroids saved to {file_path}")


def load_centroids(file_path: Optional[str] = None):
    global CENTROIDS, CENTROID_COUNTS, CENTROID_VARS, CENTROID_DENSITIES

    if file_path is None:
        file_path = current_centroid_file()

    if os.path.exists(file_path):
        data = np.load(file_path, allow_pickle=True)
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

    prev_file = os.path.join(
        CENTROID_DIR,
        CENTROID_FILE_TEMPLATE.format(yearmonth=prev_month)
    )

    if os.path.exists(prev_file):
        data = np.load(prev_file, allow_pickle=True)
        CENTROIDS = dict(data["centroids"].item())
        CENTROID_COUNTS = dict(data["counts"].item())
        CENTROID_VARS = dict(data.get("variances", {}).item())
        CENTROID_DENSITIES = dict(data.get("densities", {}).item())
        logger.info(f"Carried over centroids from {prev_file}")
    else:
        logger.warning("No centroid file found; starting fresh.")


# ---------------- Math Helpers ----------------
def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom != 0 else 0.0


def compute_density(centroid: np.ndarray, vectors: List[np.ndarray]) -> float:
    if not vectors:
        return 0.0
    sims = [cosine_similarity(v, centroid) for v in vectors]
    return float(np.mean(sims))


def global_average_density() -> float:
    if not CENTROID_DENSITIES:
        return 0.0
    return float(np.mean(list(CENTROID_DENSITIES.values())))


# ---------------- Inspection Helpers ----------------
def list_centroids() -> List[Dict[str, Any]]:
    out = []
    for cid, vec in CENTROIDS.items():
        out.append({
            "centroid_id": cid,
            "count": CENTROID_COUNTS.get(cid, 0),
            "density": CENTROID_DENSITIES.get(cid),
            "avg_variance": (
                float(np.mean(CENTROID_VARS[cid]))
                if cid in CENTROID_VARS else None
            ),
            "first_10_dims": vec[:10].tolist(),
        })
    return out


def print_centroids():
    centroids = list_centroids()
    if not centroids:
        print("No centroids loaded.")
        return

    print(f"Total centroids: {len(centroids)}\n")
    for c in centroids:
        print(
            f"{c['centroid_id']} | "
            f"count={c['count']} | "
            f"density={c['density']} | "
            f"avg_var={c['avg_variance']}"
        )


# ---------------- Drift & Split Suggestion ----------------
def centroid_drift_score(centroid_id: str) -> Optional[float]:
    if centroid_id not in CENTROID_DENSITIES:
        return None

    global_avg = global_average_density()
    if global_avg == 0:
        return None

    return CENTROID_DENSITIES[centroid_id] / global_avg


def suggest_split_candidates(
    watch_threshold: float = 0.85
) -> List[Dict[str, Any]]:
    """
    Flags centroids that appear under-dense relative to the global average.
    This function NEVER performs a split.
    """
    suggestions = []
    for cid in CENTROIDS.keys():
        score = centroid_drift_score(cid)
        if score is not None and score < watch_threshold:
            suggestions.append({
                "centroid_id": cid,
                "drift_score": round(score, 3),
                "count": CENTROID_COUNTS.get(cid, 0),
                "avg_variance": float(np.mean(CENTROID_VARS.get(cid, 0))),
            })
    return suggestions


def print_split_suggestions():
    suggestions = suggest_split_candidates()
    if not suggestions:
        print("No centroid split suggestions.")
        return

    print("Centroid split suggestions:")
    for s in suggestions:
        print(
            f"- {s['centroid_id']} | "
            f"drift={s['drift_score']} | "
            f"count={s['count']} | "
            f"avg_var={s['avg_variance']}"
        )


# ---------------- Manual Split Execution ----------------
def split_centroid(
    centroid_id: str,
    vectors: List[np.ndarray]
) -> List[str]:
    """
    MANUAL OPERATION ONLY.

    Split a centroid into two using k-means over the provided vectors.

    This function is NEVER called automatically.
    It must be invoked explicitly by a human-reviewed workflow.

    Returns:
        List of new centroid IDs.
    """
    from sklearn.cluster import KMeans

    if len(vectors) < 2:
        return [centroid_id]

    X = np.stack(vectors)
    kmeans = KMeans(n_clusters=2, random_state=42).fit(X)

    new_ids = []

    for i in range(2):
        new_vec = kmeans.cluster_centers_[i]
        new_id = f"{centroid_id}_split{i}"

        CENTROIDS[new_id] = new_vec
        idxs = np.where(kmeans.labels_ == i)[0]
        CENTROID_COUNTS[new_id] = len(idxs)
        CENTROID_VARS[new_id] = np.var(X[idxs], axis=0)
        CENTROID_DENSITIES[new_id] = float(
            np.mean([cosine_similarity(v, new_vec) for v in X[idxs]])
        )

        new_ids.append(new_id)

    # Remove old centroid
    CENTROIDS.pop(centroid_id, None)
    CENTROID_COUNTS.pop(centroid_id, None)
    CENTROID_VARS.pop(centroid_id, None)
    CENTROID_DENSITIES.pop(centroid_id, None)

    logger.info(f"Split centroid {centroid_id} into {new_ids}")
    save_centroids()

    return new_ids


# ---------------- Main Assignment Logic ----------------
def assign_to_centroid(
    vec: np.ndarray,
    similarity_threshold: float = 0.78,
    semantic_score: Optional[float] = None,
    journal_entry: Optional[dict] = None,  # NEW optional param
) -> Tuple[str, float]:
    """
    Assign a vector to the nearest centroid.

    Behavior:
    - If no centroids exist:
        → returns ("suggest_new_centroid", semantic_score)
        → NO centroid is created automatically.

    - If centroids exist:
        → assigns if similarity is strong
        → otherwise suggests new centroid (no auto-create)

    Returns:
        (label, score)
    """

    if not CENTROIDS:
        label = "suggest_new_centroid"
        score = float(semantic_score) if semantic_score is not None else 0.0
        if journal_entry is not None:
            journal_entry.setdefault("nlp", {})["assigned_centroid_id"] = label
        return label, score

    best_id = None
    best_sim = -1.0

    for cid, centroid in CENTROIDS.items():
        sim = cosine_similarity(vec, centroid)
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

        CENTROID_DENSITIES[best_id] = (
            CENTROID_DENSITIES.get(best_id, best_sim) * count + best_sim
        ) / (count + 1)

        if journal_entry is not None:
            journal_entry.setdefault("nlp", {})["assigned_centroid_id"] = best_id

        save_centroids()
        return best_id, 1.0 - best_sim

    label = "suggest_new_centroid"
    if journal_entry is not None:
        journal_entry.setdefault("nlp", {})["assigned_centroid_id"] = label

    return label, float(semantic_score) if semantic_score is not None else 1.0 - best_sim

# ---------------- REPL Convenience ----------------
def print_centroid_assignment(
    vec: np.ndarray,
    similarity_threshold: float = 0.78,
    semantic_score: Optional[float] = None,
):
    label, score = assign_to_centroid(
        vec,
        similarity_threshold=similarity_threshold,
        semantic_score=semantic_score,
    )

    print(f"Result: {label} | score={round(score, 3)}")


# ---------------- Optional Review Queue Helpers (passive) ----------------
# These are only *accessed by review_helpers.py*
# No import from review_helpers.py to centroids.py
def enqueue_split_suggestions_for_review(
    watch_threshold: float = 0.85,
    add_review_suggestion_fn=None
) -> List[str]:
    """
    Helper for external review queue. 
    `add_review_suggestion_fn` must be passed in (from review_helpers.py)
    """
    if add_review_suggestion_fn is None:
        raise ValueError("Must pass in add_review_suggestion_fn from review_helpers")

    created = []

    for s in suggest_split_candidates(watch_threshold):
        sid = add_review_suggestion_fn(
            centroid_id=s["centroid_id"],
            suggestion_type="split",
            metrics={
                "drift_score": s["drift_score"],
                "count": s["count"],
                "avg_variance": s["avg_variance"],
                "density": CENTROID_DENSITIES.get(s["centroid_id"]),
            },
        )
        created.append(sid)

    return created

def get_candidate_entries_for_centroid(centroid_id: str) -> List[str]:
    """
    Returns a list of candidate journal entries for a centroid that does not yet exist.
    Must be implemented to allow human approval of new centroid creation.
    """
    # For demonstration, this returns dummy data; replace with real journal entries retrieval
    return [f"Candidate entry {i+1}" for i in range(5)]


def create_centroid_from_samples(centroid_id: str):
    """
    Initialize a new centroid using the candidate entries attached to this centroid_id.
    For simplicity, each candidate entry is converted to a random vector.
    """
    import numpy as np

    candidates = get_candidate_entries_for_centroid(centroid_id)
    if not candidates:
        return

    # convert candidate entries to vectors (here just random placeholders)
    vectors = [np.random.rand(1024) for _ in candidates]

    # create centroid
    centroid_vec = np.mean(vectors, axis=0)
    centroids.CENTROIDS[centroid_id] = centroid_vec
    centroids.CENTROID_COUNTS[centroid_id] = len(vectors)
    centroids.CENTROID_VARS[centroid_id] = np.var(np.stack(vectors), axis=0)
    centroids.CENTROID_DENSITIES[centroid_id] = centroids.compute_density(
        centroid_vec, vectors
    )

    centroids.save_centroids()
    logger.info(f"Created new centroid {centroid_id} from candidate entries")

def get_centroid_samples(centroid_id: str, max_samples: int = 5) -> List[str]:
    """
    Return actual journal entries currently assigned to this centroid.
    You can pull from JOURNALS_FILE or from a database.
    """
    import json, os
    JOURNALS_FILE = os.path.join("data", "journals.json")
    if not os.path.exists(JOURNALS_FILE):
        return []

    with open(JOURNALS_FILE, "r", encoding="utf-8") as f:
        entries = json.load(f)

    samples = []
    for e in entries:
        if e.get("nlp", {}).get("assigned_centroid_id") == centroid_id:
            text = e.get("safe_text", "")
            if text:
                samples.append(text)
        if len(samples) >= max_samples:
            break
    return samples
