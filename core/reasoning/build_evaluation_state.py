# ==========================================
# core/reasoning/build_evaluation_state.py
# Save-state: 2026-04-24T11:48:45-04:00
# ==========================================
from typing import Dict
from .types import ConceptSignal, Inference
from pathlib import Path
import re



def build_initial_state(entry: dict) -> Dict[str, ConceptSignal]:
    state: Dict[str, ConceptSignal] = {}

    centroid_labels = _load_centroid_labels()

    for c in entry.get("centroids", []):
        concept_id = c["centroid_id"]
        weight = float(c["similarity"])

        signal = state.setdefault(concept_id, ConceptSignal(concept_id))

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
        
        label = centroid_labels.get(concept_id)
        if label:
            state[label] = signal  # same object reference
    return state

# ==========================================
# NEW: helper to load centroid_id -> label mapping (append)
# ==========================================
def _load_centroid_labels() -> Dict[str, str]:
    """
    Reads TTL files and extracts:
    centroid_id -> rdfs:label
    """
    mapping: Dict[str, str] = {}

    ttl_dir = Path("data/centroids")

    if not ttl_dir.exists():
        return mapping

    for file in ttl_dir.glob("*.ttl"):
        text = file.read_text(encoding="utf-8")

        # extract centroid_id from URN
        urn_match = re.search(r"centroid:(centroid_\d+)", text)
        label_match = re.search(r'rdfs:label\s+"([^"]+)"', text)

        if urn_match and label_match:
            cid = urn_match.group(1)
            label = label_match.group(1).strip()
            mapping[cid] = label

    return mapping