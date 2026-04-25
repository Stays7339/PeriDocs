# ==========================================
# core/reasoning/heuristic_loader.py
# Save-state: 2026-04-24T17:48:05-04:00
# ==========================================
import json
import os
import logging
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

HEURISTICS_FILE = os.path.join("data", "reasoning", "heuristics.json")


def load_heuristics() -> List[Dict[str, Any]]:
    if not os.path.exists(HEURISTICS_FILE):
        logger.info("Heuistics file could not be found!")
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