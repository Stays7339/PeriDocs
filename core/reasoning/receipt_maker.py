# ==========================================
# core/reasoning/receipt_maker.py
# Save-state: 2026-04-26T11:04:10-04:00
# ==========================================

from typing import Dict
from .types import ConceptSignal


def summarize_pool_of_active_concepts(pool_of_active_concepts: Dict[str, ConceptSignal]) -> Dict[str, float]:
    result = {}

    for concept, signal in pool_of_active_concepts.items():
        total = signal.total_weight()
        if total <= 0:
         continue # remove entries that did not produce anything above literal zero.
        result[concept] = total

    return dict(sorted(result.items(), key=lambda x: -x[1]))