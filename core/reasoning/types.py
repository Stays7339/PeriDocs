# ==========================================
# core/reasoning/types.py
# Save-state: 2026-04-22T19:54:10-04:00
# ==========================================

from __future__ import annotations
from typing import List, Optional


class Inference:
    def __init__(
        self,
        input_concepts: List[str],
        output_concept: str,
        weight: float,
        heuristic_id: str,
        step: int,
        justification: Optional[str] = None,
    ):
        self.input_concepts = input_concepts
        self.output_concept = output_concept
        self.weight = float(weight)
        self.heuristic_id = heuristic_id
        self.step = step
        self.justification = justification

    def to_dict(self):
        return {
            "input_concepts": self.input_concepts,
            "output_concept": self.output_concept,
            "weight": self.weight,
            "heuristic_id": self.heuristic_id,
            "step": self.step,
            "justification": self.justification,
        }


class ConceptSignal:
    def __init__(self, concept: str):
        self.concept = concept
        self.inferences: List[Inference] = []

    def add(self, inference: Inference):
        self.inferences.append(inference)

    def total_weight(self) -> float:
        return sum(i.weight for i in self.inferences)