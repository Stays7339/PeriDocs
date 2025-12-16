# ==========================================
# core/nlp/emotion_analysis.py
# save-state updated 2025121516
# ==========================================

import asyncio
import hashlib
import numpy as np
from typing import Dict

# ---------------- Sentence split ----------------
_SENTENCE_RE = r"[^.!?]+[.!?]?"

def _split_sentences(text: str) -> list[str]:
    import re
    return [s.strip() for s in re.findall(_SENTENCE_RE, text) if s.strip()]

# ---------------- Embedding-based placeholder ----------------
async def compute_emotion_profile_async(raw_text: str, dim: int = 1024) -> Dict[str, float]:
    from core.nlp.embeddings import get_embedding_async

    if not raw_text.strip():
        raise ValueError("Empty text provided for emotion profile")

    try:
        vec = await get_embedding_async(raw_text)
    except Exception as e:
        raise RuntimeError(f"Embedding computation failed: {e}") from e

    # placeholder: return single cluster key as mean of embedding
    h = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:8]
    profile = {h: float(np.mean(vec))}
    return profile

def normalize_emotion_profile(profile: dict) -> dict:
    if not profile:
        raise ValueError("Cannot normalize empty emotion profile")
    vals = np.array(list(profile.values()), dtype=np.float32)
    total = np.sum(vals)
    if total > 0:
        norm_vals = vals / total
    else:
        norm_vals = vals
    return dict(zip(profile.keys(), norm_vals))
