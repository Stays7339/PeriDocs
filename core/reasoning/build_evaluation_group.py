# ==========================================
# core/reasoning/build_evaluation_group.py
# Save-state: 2026-04-26T11:04:20-04:00
# ==========================================
from typing import Dict
from .types import ConceptSignal, Inference
from pathlib import Path
import re


def build_initial_evaluation_group(entry: dict) -> Dict[str, ConceptSignal]:
    pool_of_active_concepts: Dict[str, ConceptSignal] = {}

    all_concepts = _load_all_concepts()

    # --------------------------------------
    # APPLY CENTROID ACTIVATIONS
    # --------------------------------------
    for c in entry.get("centroids", []):
        raw_id = c["centroid_id"]              # "centroid_8"
        concept_id = f"centroid:{raw_id}"      # normalize → "centroid:centroid_8"
        weight = float(c["similarity"])

        if concept_id not in all_concepts:
            continue  # skip invalid concepts like precentroid_9

        signal = pool_of_active_concepts.setdefault(
            concept_id,
            ConceptSignal(concept_id)
        )

        signal.add(
            Inference(
                input_concepts=[],
                output_concept=concept_id,
                weight=weight,
                heuristic_id="centroid_similarity",
                step=0,
                justification="embedding similarity",
            )
        )

    return pool_of_active_concepts
# ==========================================
def _load_all_concepts() -> Dict[str, str]:
    mapping: Dict[str, str] = {}

    ttl_dir = Path("data/reasoning")

    if not ttl_dir.exists():
        return mapping

    for file in ttl_dir.glob("*.ttl"):
        text = file.read_text(encoding="utf-8")

        # ONLY match subject URN
        urn_match = re.search(r"<urn:peridocs:([^>]+)>\s+a\s+", text)
        label_match = re.search(r'rdfs:label\s+"([^"]+)"', text)

        if not urn_match:
            continue

        cid = urn_match.group(1)
        label = label_match.group(1).strip() if label_match else cid

        mapping[cid] = label

    return mapping