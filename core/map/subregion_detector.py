# ==========================================
# core/map/subregion_detector.py
# Save-state: 2026-04-15T15:42:30-04:00
#
# Runtime density-based subregion detector
# (CentroidSystem + EntryWritingRuntime aware)
# ==========================================

import logging
from typing import Dict, Any, List, Tuple

import numpy as np

from core.map.mapping_runtime import centroid_system, entry_runtime

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# Utility: embedding hydration from runtime
# ------------------------------------------------------------

async def _hydrate_vectors(entry_ids: List[str]) -> Tuple[np.ndarray, List[str]]:
    """
    Resolve entry_ids → embeddings using runtime-only source of truth.

    Returns:
        - vectors array (N x 1024)
        - aligned entry_ids (filtered for missing embeddings if any)
    """

    vectors = []
    resolved_ids = []

    for eid in entry_ids:
        vec = await entry_runtime.get_embedding(eid)
        if vec is None:
            continue

        vectors.append(vec)
        resolved_ids.append(eid)

    if not vectors:
        return np.array([]), []

    return np.vstack(vectors), resolved_ids


# ------------------------------------------------------------
# Core geometry helpers
# ------------------------------------------------------------

def _normalize(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v, axis=1, keepdims=True) + 1e-12
    return v / norm


def _cosine_similarity_matrix(v: np.ndarray) -> np.ndarray:
    v = _normalize(v)
    return np.dot(v, v.T)


def _density_components(sim: np.ndarray, threshold: float) -> List[List[int]]:
    """
    Lightweight connected-components clustering over similarity graph.
    """
    n = sim.shape[0]
    visited = set()
    components = []

    for i in range(n):
        if i in visited:
            continue

        stack = [i]
        group = []

        while stack:
            current = stack.pop()
            if current in visited:
                continue

            visited.add(current)
            group.append(current)

            for j in range(n):
                if j not in visited and sim[current][j] >= threshold:
                    stack.append(j)

        components.append(group)

    return components


# ------------------------------------------------------------
# Main detector
# ------------------------------------------------------------

async def detect_subregions(
    centroid_id: str,
    similarity_threshold: float = 0.72,
    min_region_size: int = 3,
) -> Dict[str, Any]:
    """
    Detect dense semantic subregions inside a centroid.

    This is:
        - fully runtime-based
        - deterministic given embeddings + membership
        - non-persistent
        - non-authoritative (suggestion layer only)

    Data sources:
        - centroid_system: membership structure (entry_ids)
        - entry_runtime: embeddings (1024-d vectors)
    """

    centroid = centroid_system._centroids.get(centroid_id)
    if centroid is None:
        return {"centroid_id": centroid_id, "regions": [], "reason": "missing centroid"}

    entry_ids = getattr(centroid.current, "entry_ids", [])
    if not entry_ids:
        return {"centroid_id": centroid_id, "regions": [], "reason": "empty centroid"}

    vectors, resolved_ids = await _hydrate_vectors(entry_ids)

    if len(resolved_ids) < min_region_size:
        return {
            "centroid_id": centroid_id,
            "regions": [],
            "reason": "insufficient hydrated embeddings",
        }

    sim = _cosine_similarity_matrix(vectors)
    groups = _density_components(sim, similarity_threshold)

    regions = []

    for group in groups:
        if len(group) < min_region_size:
            continue

        idx_vectors = vectors[group]
        center = np.mean(idx_vectors, axis=0)

        regions.append({
            "size": len(group),
            "entry_ids": [resolved_ids[i] for i in group],
            "representative_vector": center.tolist(),
            "density_threshold": similarity_threshold,
        })

    return {
        "centroid_id": centroid_id,
        "region_count": len(regions),
        "regions": regions,
    }