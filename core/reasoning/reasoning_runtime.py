# ==========================================
# core/reasoning/reasoning_runtime.py
# Save-state: 2026-04-25T23:24:25-04:00
# ==========================================

from typing import Dict, Any, List
from .build_evaluation_group import build_initial_evaluation_group
from .heuristic_loader import load_heuristics
from .evaluator import evaluate_heuristic
from .damping import apply_damping
from .receipt_maker import summarize_pool_of_active_concepts
from .types import ConceptSignal, Inference
from .evaluator import integrate_inference


MIN_MEANINGFUL_WEIGHT = 0.01
MAX_STEPS = 6  # safety cap


async def run_reasoning(entry: Dict[str, Any]) -> Dict[str, Any]:
    pool_of_active_concepts: Dict[str, ConceptSignal] = build_initial_evaluation_group(entry)
    heuristics = load_heuristics()

    receipt: List[dict] = []

    step = 1

    while step <= MAX_STEPS:
        new_inferences: List[Inference] = []

        for h in heuristics:
            results = evaluate_heuristic(pool_of_active_concepts, h, step)
            new_inferences.extend(results)

        if not new_inferences:
            break

        meaningful = False

        for inf in new_inferences:
            changed = integrate_inference(pool_of_active_concepts, inf)

            if not changed:
                continue

            if inf.weight < MIN_MEANINGFUL_WEIGHT:
                continue

            receipt.append(inf.to_dict())
            meaningful = True

        if not meaningful:
            break

        step += 1

    return {
        "final_concepts": summarize_pool_of_active_concepts(pool_of_active_concepts),
        "receipt": receipt,
    }