# ==========================================
# core/reasoning/reasoning_runtime.py
# Save-state: 2026-04-22T20:00:40-04:00
# ==========================================

from typing import Dict
from .types import ConceptSignal


def summarize_state(state: Dict[str, ConceptSignal]) -> Dict[str, float]:
    result = {}

    for concept, signal in state.items():
        total = signal.total_weight()
        result[concept] = total

    return dict(sorted(result.items(), key=lambda x: -x[1]))