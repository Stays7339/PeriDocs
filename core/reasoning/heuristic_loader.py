# ==========================================
# core/reasoning/heuristic_loader.py
# Save-state: 2026-04-22T19:54:15-04:00
# ==========================================
import json
from pathlib import Path
from typing import List, Dict, Any

HEURISTICS_PATH = Path("data/heuristics.json")


def load_heuristics() -> List[Dict[str, Any]]:
    if not HEURISTICS_PATH.exists():
        return []

    with open(HEURISTICS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # basic validation
    cleaned = []
    for h in data:
        if "heuristic_id" not in h:
            continue
        if "givens" not in h or "outputs" not in h:
            continue
        cleaned.append(h)

    return cleaned