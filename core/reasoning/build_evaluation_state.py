# ==========================================
# core/reasoning/build_evaluation_state.py
# Save-state: 2026-04-22T20:03:50-04:00
# ==========================================
from typing import Dict
from .types import ConceptSignal, Inference


def build_initial_state(entry: dict) -> Dict[str, ConceptSignal]:
    state: Dict[str, ConceptSignal] = {}

    for c in entry.get("centroids", []):
        concept = c["centroid_id"]
        weight = float(c["similarity"])

        signal = state.setdefault(concept, ConceptSignal(concept))

        signal.add(
            Inference(
                input_concepts=[],
                output_concept=concept,
                weight=weight,
                heuristic_id="centroid_similarity",
                step=0,
                justification="embedding similarity",
            )
        )

    return state