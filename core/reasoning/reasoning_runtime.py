# ==========================================
# core/reasoning/reasoning_runtime.py
# Save-state: 2026-07-12T17:29-04:00
# ==========================================

import os
import json
import asyncio
from typing import Dict, Any, List


from core import database
from core.mode_lock import SystemModeLock  # Enforces DB vs Flat-File runtime constraint
from .build_evaluation_group import build_initial_evaluation_group
from .heuristic_loader import registry
from .evaluator import evaluate_heuristic
from .damping import apply_damping
from .receipt_maker import summarize_pool_of_active_concepts
from .types import ConceptSignal, Inference
from .evaluator import integrate_inference


MIN_MEANINGFUL_WEIGHT = 0.01
MAX_STEPS = 6  # safety cap
RESOURCES_JSON_FILE = os.path.join("data", "reasoning", "resources.json")

async def run_reasoning(entry: Dict[str, Any]) -> Dict[str, Any]:
    # 1. ALWAYS initialize the registry before accessing data
    if not registry._initialized:
        await registry.initialize(database.db_engine)

    pool_of_active_concepts: Dict[str, ConceptSignal] = build_initial_evaluation_group(entry)
    
    # 2. Access the list directly from the registry
    heuristics = registry._heuristics

    receipt: List[dict] = []
    step = 1

    # Main iterative inference engine loop
    while step <= MAX_STEPS:
        new_inferences: List[Inference] = []

        # Now this loop works perfectly with your registry data
        for h in heuristics:
            results = evaluate_heuristic(pool_of_active_concepts, h, step)
            new_inferences.extend(results)

        if not new_inferences:
            break

        # =========================================================================
        # OPTION 1: CUMULATIVE STEP SIGNIFICANCE TRACKING
        # =========================================================================
        step_cumulative_weight = 0.0
        step_buffered_receipts = []

        for inf in new_inferences:
            changed = integrate_inference(pool_of_active_concepts, inf)

            if not changed:
                continue

            # Track every inference that successfully advanced or adjusted the pool
            step_cumulative_weight += inf.weight
            step_buffered_receipts.append(inf.to_dict())

        # Circuit breaker check: did this round of deductions achieve a critical mass?
        if step_cumulative_weight >= MIN_MEANINGFUL_WEIGHT:
            receipt.extend(step_buffered_receipts)
        else:
            # Drop out early if the collective signal generation is purely negligible noise
            break

        step += 1

    # Extract completed scores from the evaluation layer
    final_concepts = summarize_pool_of_active_concepts(pool_of_active_concepts)
    culled_resources = []

    if final_concepts:
        # =========================================================================
        # DUAL PERSISTENCE CULLING STRATEGY
        # =========================================================================
        
        # CASE A: POSTGRESQL ENGINE MODE
        if SystemModeLock.resolve_operational_mode() == "DATABASE":
            try:
                active_concept_ids = list(final_concepts.keys())
                async with db_engine.pool.connection() as conn:
                    # Query matches concepts against our active concept array mapping
                    query = """
                        SELECT r.resource_id, r.title, r.url, r.resource_type, r.description, r.created_at,
                               array_agg(m.concept_id) as assigned_concepts
                        FROM kb_schema.external_resources r
                        JOIN kb_schema.resource_concept_mappings m ON r.resource_id = m.resource_id
                        WHERE m.concept_id = ANY($1)
                        GROUP BY r.resource_id;
                    """
                    rows = await conn.fetch(query, active_concept_ids)
                    
                    for row in rows:
                        assigned = row["assigned_concepts"] or []
                        # Combine weights of all overlapping active concepts
                        combined_weight = sum(final_concepts[c] for c in assigned if c in final_concepts)
                        
                        if combined_weight > 0:
                            culled_resources.append({
                                "resource_id": str(row["resource_id"]),
                                "title": row["title"],
                                "url": row["url"],
                                "resource_type": row["resource_type"],
                                "description": row["description"] or "",
                                "assigned_concepts": assigned,
                                "created_at": row["created_at"].isoformat() if row["created_at"] else "",
                                "relevance_weight": combined_weight
                            })
            except Exception:
                culled_resources = []

        # CASE B: FLAT-FILE MODE (JSON/NPZ)
        else:
            try:
                if os.path.exists(RESOURCES_JSON_FILE):
                    loop = asyncio.get_event_loop()
                    resources_list = await loop.run_in_executor(None, lambda: json.load(open(RESOURCES_JSON_FILE, "r")))
                else:
                    resources_list = []

                for r in resources_list:
                    assigned = r.get("assigned_concepts", [])
                    # Combine weights of all overlapping active concepts
                    combined_weight = sum(final_concepts[c] for c in assigned if c in final_concepts)
                    
                    if combined_weight > 0:
                        r_copy = dict(r)
                        r_copy["relevance_weight"] = combined_weight
                        culled_resources.append(r_copy)
            except Exception:
                culled_resources = []

        # Sort the resources in descending order based on combined weight
        culled_resources.sort(key=lambda x: x.get("relevance_weight", 0.0), reverse=True)

    # Return elements structured sequentially in your preferred dictionary signature
    return {
        "culled_resource_list": culled_resources,
        "final_concepts": final_concepts,
        "receipt": receipt,
    }