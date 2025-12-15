"""
app/helpers/top_matches.py

API-ready top matches + JSON-safe outputs based on vector similarity,
repetition, and sentiment adjustments.
"""

from typing import List, Dict, Any
from app.helpers.similarity import compute_similarity
from app.helpers.json_safe import json_safe

def find_top_matches(
    entry_vec: list,
    all_entries: list,
    top_n: int = 20
) -> list:
    scored_entries = []

    for e in all_entries:
        vec = e.get('nlp', {}).get('embedding')
        if vec is None:
            continue
        similarity = compute_similarity(entry_vec, vec)
        scored_entries.append({"entry": e, "score": similarity})

    scored_entries.sort(key=lambda x: x['score'], reverse=True)
    return [json_safe(e['entry']) for e in scored_entries[:top_n]]
