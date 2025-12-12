# =============================================================
# core/nlp/emotion_analysis.py
# Updated 2025-12-12 — analysis layer that uses emotion_model
# =============================================================
"""
Async emotion analysis wrapper for PeriDocs.

Responsibilities:
- Sentence-splitting and per-sentence aggregation.
- Calls compute_emotion_distribution() from emotion_model.
- Normalizes distributions for downstream use.
- Exposes helpers that process_entry.py and routes can call.
"""

import re
from typing import Dict, List, Any
import numpy as np
from core.nlp import emotion_model
import asyncio

_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]?")

def _split_sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_RE.findall(text) if s.strip()]

def normalize_emotion_profile(emotion_dict: Dict[str, float]) -> Dict[str, float]:
    """
    Normalize values to a sum of 1. If empty, return {}.
    Keeps deterministic behaviour (no random smoothing).
    """
    if not emotion_dict:
        return {}
    # sanitize numeric values
    clean = {k: float(v) for k, v in emotion_dict.items() if v is not None and not np.isnan(v)}
    total = sum(clean.values())
    if total <= 0:
        return {k: 0.0 for k in clean}
    return {k: float(v) / total for k, v in clean.items()}

async def analyze_emotions_async(raw_text: str) -> Dict[str, Any]:
    """
    Process raw text:
    - Split sentences
    - For each sentence, request emotion_model.compute_emotion_distribution
    - Aggregate probabilities across sentences (simple sum) and normalize
    - Return dict { "emotions": normalized_dist, "pending_candidates": [...] }
    """
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return {"emotions": {}, "pending_candidates": sorted(list(emotion_model.pending_candidates()))}

    sentences = _split_sentences(raw_text)
    aggregated: Dict[str, float] = {}

    # sequential deterministic processing (could be parallelized but then ensure deterministic ordering)
    for s in sentences:
        dist = await emotion_model.compute_emotion_distribution(s)
        for k, v in dist.items():
            aggregated[k] = aggregated.get(k, 0.0) + float(v)

    normalized = normalize_emotion_profile(aggregated)
    pending = sorted(list(emotion_model.pending_candidates()))
    return {"emotions": normalized, "pending_candidates": pending}

# sync wrapper
def analyze_emotions(text: str) -> Dict[str, Any]:
    return asyncio.get_event_loop().run_until_complete(analyze_emotions_async(text))
