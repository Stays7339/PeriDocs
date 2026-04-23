# ==========================================
# core/reasoning/reasoning_runtime.py
# Save-state: 2026-04-22T19:59:15-04:00
# ==========================================

from typing import Dict, Any, List
from .state import build_initial_state
from .heuristic_loader import load_heuristics
from .evaluator import evaluate_heuristic
from .damping import apply_damping
from .receipt import summarize_state
from .types import ConceptSignal, Inference


MIN_MEANINGFUL_WEIGHT = 0.01
MAX_STEPS = 6  # safety cap


async def run_reasoning(entry: Dict[str, Any]) -> Dict[str, Any]:
    state: Dict[str, ConceptSignal] = build_initial_state(entry)
    heuristics = load_heuristics()

    receipt: List[dict] = []

    step = 1

    while step <= MAX_STEPS:
        new_inferences: List[Inference] = []

        for h in heuristics:
            results = evaluate_heuristic(state, h, step)
            new_inferences.extend(results)

        if not new_inferences:
            break

        meaningful = False

        for inf in new_inferences:
            signal = state.setdefault(inf.output_concept, ConceptSignal(inf.output_concept))

            adjusted_weight = apply_damping(len(signal.inferences), inf.weight)

            if adjusted_weight < MIN_MEANINGFUL_WEIGHT:
                continue

            inf.weight = adjusted_weight
            signal.add(inf)

            receipt.append(inf.to_dict())
            meaningful = True

        if not meaningful:
            break

        step += 1

    return {
        "final_concepts": summarize_state(state),
        "receipt": receipt,
    }