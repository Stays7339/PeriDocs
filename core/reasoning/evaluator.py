# ==========================================
# core/reasoning/evaluator.py
# Save-state: 2026-07-05T15:20-04:00
# ==========================================

from __future__ import annotations

from typing import Dict, List, Any
import math
import hashlib

from .types import Inference, ConceptSignal


# -----------------------------
# CONFIGURATION (tunable knobs)
# -----------------------------

SOFT_OR_TEMPERATURE = 3.0
PATH_DIVERSITY_WEIGHT = 0.30
MIN_ACTIVATION_EPSILON = 1e-9 #essentially a mathematical seatbelt for logarithmic functions.

# NEW: Controls how many required inputs must be active for a heuristic to fire.
# 0.70 means 70% of the listed 'givens' must be satisfied to pass the gate.
MIN_ACTIVATION_RATIO = 0.75 


# -----------------------------
# SOFT OR ACTIVATION
# -----------------------------

def soft_or(scores: List[float]) -> float:
    """
    Soft OR via numerically stable log-sum-exp approximation.

    Behavior:
    - max-like when one strong signal dominates
    - additive when multiple moderate signals exist
    - never collapses to strict averaging
    """
    if not scores:
        return 0.0

    # shift for numerical stability
    m = max(scores)

    # log-sum-exp trick
    total = sum(math.exp((s - m) / SOFT_OR_TEMPERATURE) for s in scores)

    return m + SOFT_OR_TEMPERATURE * math.log(total + MIN_ACTIVATION_EPSILON)


# -----------------------------
# PATH ID GENERATION (UPDATED FOR STABLE LINEAGE)
# -----------------------------

def make_path_id(
    heuristic_id: str,
    input_concepts: List[str],
    output_concept: str
) -> str:
    """
    Deterministic path identifier for tracing stable reasoning routes.

    Removed the 'step' parameter to ensure that Steps 1 through 6 of 
    the exact same logical deduction branch share a stable identity.
    """
    raw = f"{heuristic_id}|{sorted(input_concepts)}|{output_concept}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# -----------------------------
# PATH DIVERSITY
# -----------------------------

def path_diversity(signal: ConceptSignal) -> float:
    """
    Measures diversity of reasoning routes that produced a concept.

    High value = many independent heuristic pathways.
    Low value = repetition of same reasoning source.
    """
    paths = getattr(signal, "heuristic_paths", None)
    if not paths:
        return 0.0

    values = list(paths.values())
    total = sum(values)

    if total <= 0:
        return 0.0

    entropy = 0.0
    for v in values:
        p = v / total
        entropy -= p * math.log(p + MIN_ACTIVATION_EPSILON)

    return entropy


# -----------------------------
# CORE HEURISTIC EXECUTION
# -----------------------------

def evaluate_heuristic(
    pool_of_active_concepts: Dict[str, ConceptSignal],
    heuristic: Dict[str, Any],
    step: int
) -> List[Inference]:
    """
    Executes a single heuristic over the current concept pool_of_active_concepts.

    Produces INFERENCES (ephemeral reasoning edges).
    """
    heuristic_id = heuristic["heuristic_id"]
    givens = heuristic.get("givens", [])
    outputs = heuristic.get("outputs", [])

    if not givens:
        return []

    # -----------------------------
    # COLLECT INPUT SIGNALS
    # -----------------------------
    input_scores: List[float] = []
    resolved_inputs: List[str] = []

    for concept in givens:
        signal = pool_of_active_concepts.get(concept)
        if not signal:
            continue

        resolved_inputs.append(concept)
        input_scores.append(signal.total_weight())

    # -----------------------------
    # RATIO ACTIVATION GATE CHECK
    # -----------------------------
    # Protects against semantic drift by verifying the proportion of triggered inputs.
    match_ratio = len(resolved_inputs) / len(givens)
    if match_ratio < MIN_ACTIVATION_RATIO:
        return []

    # -----------------------------
    # SOFT OR ACTIVATION
    # -----------------------------
    activation = soft_or(input_scores)
    results: List[Inference] = []

    # -----------------------------
    # EMIT OUTPUT INFERENCES
    # -----------------------------
    for out in outputs:
        output_concept = out.get("concept")
        base_likelihood = float(out.get("likelihood", 0.0))

        if not output_concept:
            continue

        raw_weight = activation * base_likelihood

        if raw_weight <= 0:
            continue

        # Uses the newly stabilized tracking footprint (omitting step counter)
        path_id = make_path_id(
            heuristic_id=heuristic_id,
            input_concepts=resolved_inputs,
            output_concept=output_concept,
        )

        inference = Inference(
            input_concepts=resolved_inputs,
            output_concept=output_concept,
            weight=raw_weight,
            heuristic_id=heuristic_id,
            step=step,
            justification=out.get("justification"),
            path_id=path_id,
        )

        results.append(inference)

    return results


# -----------------------------
# APPLY PATH DIVERSITY BONUS
# -----------------------------

def apply_path_diversity_bonus(signal: ConceptSignal, weight: float) -> float:
    """
    Adjust weight based on diversity of reasoning paths.
    """
    diversity = path_diversity(signal)
    return weight * (1.0 + diversity * PATH_DIVERSITY_WEIGHT)


# -----------------------------
# MAIN EVALUATION LOOP ENTRYPOINT
# -----------------------------

def integrate_inference(
    pool_of_active_concepts: Dict[str, ConceptSignal],
    inference: Inference
) -> bool:
    """
    Inserts inference into pool_of_active_concepts with damping and tracking.
    """
    from .damping import apply_damping  # local import to avoid cycles

    concept = inference.output_concept
    signal = pool_of_active_concepts.setdefault(concept, ConceptSignal(concept))

    # DAMPING (repetition decay)
    damped = apply_damping(len(signal.inferences), inference.weight)

    # PATH DIVERSITY BONUS
    adjusted = apply_path_diversity_bonus(signal, damped)

    if adjusted <= 0:
        return False

    inference.weight = adjusted
    signal.add(inference)

    # PATH TRACKING
    if not hasattr(signal, "heuristic_paths"):
        signal.heuristic_paths = {}

    signal.heuristic_paths[inference.heuristic_id] = (
        signal.heuristic_paths.get(inference.heuristic_id, 0.0) + adjusted
    )

    return True


# -----------------------------
# pool_of_active_concepts UPDATE FROM HEURISTICS
# -----------------------------

def run_heuristics_step(
    pool_of_active_concepts: Dict[str, ConceptSignal],
    heuristics: List[Dict[str, Any]],
    step: int
) -> List[Inference]:
    """
    Runs all heuristics for a single step.
    """
    all_inferences: List[Inference] = []

    for h in heuristics:
        inferences = evaluate_heuristic(pool_of_active_concepts, h, step)
        all_inferences.extend(inferences)

    return all_inferences


# -----------------------------
# FULL REDUCTION PASS
# -----------------------------

def apply_inferences(
    pool_of_active_concepts: Dict[str, ConceptSignal],
    inferences: List[Inference]
) -> List[Inference]:
    """
    Applies all inferences into pool_of_active_concepts and returns only those that changed pool_of_active_concepts.
    """

    applied: List[Inference] = []

    for inf in inferences:
        changed = integrate_inference(pool_of_active_concepts, inf)
        if changed:
            applied.append(inf)

    return applied