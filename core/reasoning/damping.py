# ==========================================
# core/reasoning/damping.py
# Save-state: 2026-04-22T20:03:50-04:00
# ==========================================

def apply_damping(existing_count: int, new_weight: float) -> float:
    """
    Diminishing returns:
    - First few signals matter more
    - Later repetitions decay
    """
    damping_factor = 1.0 / (1.0 + 0.5 * existing_count)
    return new_weight * damping_factor