# ==========================================
# core/reasoning/heuristic_loader.py
# Save-state: 2026-04-24T14:57:05-04:00
# ==========================================
import json
import os
from pathlib import Path
from typing import List, Dict, Any

HEURISTICS_FILE = os.path.join("data", "reasoning_data", "heuristics.json")


def load_heuristics() -> List[Dict[str, Any]]:
    if not HEURISTICS_FILE.exists():
        return []

    with open(HEURISTICS_FILE, "r", encoding="utf-8") as f:
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