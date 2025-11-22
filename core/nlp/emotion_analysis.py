"""
core/nlp/emotion_analysis.py

Emotion analysis module for PeriDocs.

Handles:
- Numeric weighting, normalization, and summary of emotion distributions.
- Valence/arousal mapping.
- Modified intensity scores using simplified intensifiers/deintensifiers.
- Lexicon constants are imported from anchors.py (empty placeholders here).

Backward compatibility: compute_sentiment_from_profile() replaces sentiment_analysis.py.
"""

import numpy as np
import re
import asyncio
from typing import Dict, Set, Optional
from math import tanh
from core.nlp.embeddings import get_embedding, batch_embeddings_async
from core.nlp.anchors import get_emotion_anchor
from core.nlp.fuzzy_utils import get_combined_lexicons

# -------------------------------
# INTENSIFIERS & DEINTENSIFIERS (streamlined)
# -------------------------------
_INTENSIFIERS: Set[str] = {"very", "extremely", "really", "super", "ultra"}
_DEINTENSIFIERS: Set[str] = {"slightly", "somewhat", "a bit", "barely"}

# -------------------------------
# EMOTION ANCHORS (empty placeholders; lexicons live in anchors.py)
# -------------------------------
_EMOTION_LEXICONS: Dict[str, Set[str]] = {
    "joy": get_emotion_anchor("joy"),
    "sadness": get_emotion_anchor("sadness"),
    "anger": get_emotion_anchor("anger"),
    "fear": get_emotion_anchor("fear"),
    "disgust": get_emotion_anchor("disgust"),
    "surprise": get_emotion_anchor("surprise")
}

# -------------------------------
# UTILITY FUNCTIONS
# -------------------------------
def normalize_vector(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v)
    if norm == 0 or np.isnan(norm):
        return np.zeros_like(v)
    return v / norm

def sigmoid(x: float) -> float:
    return 1 / (1 + np.exp(-x))

# -------------------------------
# ASYNC HELPER
# -------------------------------
def run_async(func, *args, **kwargs):
    """
    Safely runs an async function from sync context.
    Handles existing event loops without crashing.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Inside an active loop; create a task and wait
        future = asyncio.ensure_future(func(*args, **kwargs))
        return asyncio.get_event_loop().run_until_complete(future)
    else:
        return asyncio.run(func(*args, **kwargs))

async def get_embedding_async(text: str, model_name: str = "all-roberta-large-v1") -> np.ndarray:
    """
    Placeholder async wrapper for future async endpoints.
    Currently calls synchronous get_embedding for compatibility.
    """
    return get_embedding(text, model_name)

# -------------------------------
# EMOTION COMPUTATION CORE
# -------------------------------
def compute_emotion_profile(
    text: str,
    emotion_analysis: Optional[Dict[str, Set[str]]] = None,
    model_name: str = "all-roberta-large-v1"
) -> Dict[str, float]:
    """
    Computes emotion distribution for a given text using embeddings.
    Uses the passed `emotion_analysis` lexicon or defaults to combined anchors.
    """
    combined_lexicons = get_combined_lexicons(_EMOTION_LEXICONS)
    lexicon = emotion_analysis or combined_lexicons
    emotions = list(lexicon.keys())

    if not text.strip():
        return {emotion: 0.0 for emotion in emotions}

    try:
        text_vec = get_embedding(text, model_name)
        lexicon_vecs = {}
        for emo, words in lexicon.items():
            word_list = list(words)  # <-- FIX: convert set to list for deterministic iteration
            vecs = run_async(batch_embeddings_async, word_list)
            if vecs.size == 0:
                print(f"[WARNING] No embeddings returned for lexicon '{emo}' | words: {word_list}")
            lexicon_vecs[emo] = vecs

    except Exception as e:
        # Propagate errors instead of silently returning zeros
        raise RuntimeError(f"Embedding computation failed: {e}")

    scores = {}
    for emo, vectors in lexicon_vecs.items():
        similarities = np.dot(vectors, text_vec) / (
            np.linalg.norm(vectors, axis=1) * np.linalg.norm(text_vec) + 1e-9
        )
        similarities = np.clip(similarities, -1, 1)
        scores[emo] = float(np.mean(similarities))

    # -------------------------------
    # Deterministic Softmax (DSMX)
    # -------------------------------
    raw_vals = np.array(list(scores.values()), dtype=float)

    # Replace NaN or exact zeros with a tiny positive floor
    min_floor = 1e-3
    raw_vals = np.where(np.isnan(raw_vals) | (raw_vals == 0), min_floor, raw_vals)

    # Safety: ensure not-all-zero fallback
    if np.allclose(raw_vals, 0):
        raw_vals[:] = min_floor

    # Temperature (τ): lower = sharper, higher = flatter
    tau = 0.85

    # Centering + temperature scaling
    centered = (raw_vals - np.max(raw_vals)) / max(tau, 1e-9)

    # Deterministic tie-breaker:
    tie_break = np.array([hash(e) % 10_000 for e in emotions], dtype=float) * 1e-12
    centered = centered + tie_break

    exp_vals = np.exp(centered)
    probs = exp_vals / (np.sum(exp_vals) + 1e-9)

    return dict(zip(emotions, probs))

# -------------------------------
# VALENCE & AROUSAL SUMMARY
# -------------------------------
def summarize_valence_arousal(emotion_profile: Dict[str, float]) -> Dict[str, float]:
    valence_map = {
        "joy": 1.0, "trust": 0.7, "anticipation": 0.5,
        "anger": -0.8, "disgust": -0.9, "sadness": -1.0,
        "fear": -0.7, "surprise": 0.2
    }
    arousal_map = {
        "joy": 0.6, "trust": 0.3, "anticipation": 0.8,
        "anger": 0.9, "disgust": 0.7, "sadness": 0.2,
        "fear": 0.8, "surprise": 1.0
    }

    valence = sum(emotion_profile.get(e, 0) * valence_map.get(e, 0) for e in emotion_profile)
    arousal = sum(emotion_profile.get(e, 0) * arousal_map.get(e, 0) for e in emotion_profile)

    return {
        "valence": sigmoid(valence * 3),
        "arousal": np.clip(arousal, 1e-6, 1.0)
    }

# -------------------------------
# INTENSITY MODIFIERS
# -------------------------------
def apply_intensity_modifiers(text: str, base_profile: Dict[str, float]) -> Dict[str, float]:
    if not text:
        return base_profile

    modified = base_profile.copy()
    text_lower = text.lower()

    for intens in _INTENSIFIERS:
        if re.search(rf"\b{re.escape(intens)}\b['’.,!?]?", text_lower):
            for k in modified:
                modified[k] *= 1.2

    for deintens in _DEINTENSIFIERS:
        if re.search(rf"\b{re.escape(deintens)}\b['’.,!?]?", text_lower):
            for k in modified:
                modified[k] *= 0.8

    total = sum(modified.values())
    if total > 0:
        modified = {k: v / total for k, v in modified.items()}

    return modified

# -------------------------------
# MASTER PIPELINE
# -------------------------------
def analyze_emotions(text: str) -> Dict[str, Dict[str, float]]:
    base_profile = compute_emotion_profile(text)
    adjusted_profile = apply_intensity_modifiers(text, base_profile)
    summary = summarize_valence_arousal(adjusted_profile)

    return {
        "emotion_distribution": adjusted_profile,
        "valence_arousal_summary": summary
    }

# -------------------------------
# PUBLIC API
# -------------------------------
def get_emotion_anchors() -> Dict[str, Set[str]]:
    return _EMOTION_LEXICONS

def get_intensifiers() -> Set[str]:
    return _INTENSIFIERS

def get_deintensifiers() -> Set[str]:
    return _DEINTENSIFIERS

# -------------------------------
# BACKWARD COMPATIBILITY
# -------------------------------
def emotion_profile(text: str) -> Dict[str, Dict[str, float]]:
    return analyze_emotions(text)

def compute_sentiment_from_profile(emotion_summary: Dict[str, float]) -> Dict[str, float]:
    valence = emotion_summary.get("valence", 0.0)
    arousal = emotion_summary.get("arousal", 1.0)
    polarity = tanh(valence / max(1e-6, arousal))
    if polarity >= 0.05:
        label = "positive"
    elif polarity <= -0.05:
        label = "negative"
    else:
        label = "neutral"
    return {"polarity": float(polarity), "label": label, "source": "emotion-profile"}
