"""
core/nlp/emotion_analysis.py
------------------
Computes normalized emotion distributions, valence/arousal summaries,
and modified intensity scores for given text using hybrid
embedding-lexicon analysis. Lexicon constants are imported from anchors.py.
"""

import numpy as np
import re
from typing import Dict, Set, Optional
from math import tanh
from core.nlp.embeddings import get_embedding, batch_embeddings
from core.nlp.anchors import get_emotion_anchor
from core.nlp.fuzzy_utils import get_combined_lexicons

# -------------------------------
# INTENSIFIERS & DEINTENSIFIERS
# -------------------------------
_INTENSIFIERS: Set[str] = {
    "very", "extremely", "really", "super", "mega", "ultra", "hella", "wicked", "mad", "damn",
    "totally", "absolutely", "completely", "entirely", "wholly", "thoroughly", "purely",
    "incredibly", "seriously", "ridiculously", "insanely", "wildly", "crazily", "tremendously",
    "vastly", "extraordinarily", "phenomenally", "beyond", "especially", "overwhelmingly",
    "intensely", "powerfully", "deeply", "so", "heaping", "freaking", "absurdly", "notably",
    "strikingly", "severely", "exponentially", "monumentally", "outlandishly", "excessively",
    "passionately", "strongly", "mightily"
}

_DEINTENSIFIERS: Set[str] = {
    "slightly", "somewhat", "kind of", "sort of", "a little", "a bit", "barely", "hardly",
    "mildly", "faintly", "loosely", "gently", "modestly", "softly", "quietly", "weakly", "thinly",
    "tenuously", "partially", "incompletely", "fractionally", "semi", "quasi", "not really",
    "not much", "only a little", "just a touch", "halfway", "tepidly", "limply", "almost",
    "nearly", "practically", "virtually", "kindasorta", "lowkey", "vaguely", "barely-there",
    "meh", "subduedly", "temperedly", "cautiously", "lightly", "marginally", "minutely",
    "slowly", "hesitantly", "passably"
}

# -------------------------------
# EMOTION ANCHORS
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
# EMOTION COMPUTATION CORE
# -------------------------------
def compute_emotion_profile(
    text: str,
    emotion_analysis: Optional[Dict[str, Set[str]]] = None,
    model_name: str = "all-MiniLM-L6-v2"
) -> Dict[str, float]:
    """
    Computes emotion distribution for a given text using embeddings.
    Uses the passed `emotion_analysis` lexicon or defaults to combined anchors.
    Prints debug info for lexicons and vector norms.
    """
    combined_lexicons = get_combined_lexicons(_EMOTION_LEXICONS)
    lexicon = emotion_analysis or combined_lexicons
    emotions = list(lexicon.keys())

    if not text.strip():
        print("DEBUG: Empty input string; returning zeros.")
        return {emotion: 0.0 for emotion in emotions}

    try:
        text_vec = get_embedding(text, model_name)
        print(f"DEBUG: Text embedding norm: {np.linalg.norm(text_vec):.6f}")
        lexicon_vecs = {emo: batch_embeddings(words, model_name) for emo, words in lexicon.items()}
        for emo, vecs in lexicon_vecs.items():
            norms = np.linalg.norm(vecs, axis=1)
            print(f"DEBUG: {emo} lexicon vector norms (first 5): {norms[:5]}")
    except Exception:
        print("DEBUG: Embeddings failed; returning zeros.")
        return {emotion: 0.0 for emotion in emotions}

    # Compute cosine similarities as before
    scores = {}
    for emo, vectors in lexicon_vecs.items():
        similarities = np.dot(vectors, text_vec) / (
            np.linalg.norm(vectors, axis=1) * np.linalg.norm(text_vec) + 1e-9
        )
        similarities = np.clip(similarities, -1, 1)
        scores[emo] = float(np.mean(similarities))

    # Convert raw cosine similarity scores to probability distribution
    raw_vals = np.array(list(scores.values()))

    # PATCH: Ensure non-zero floor for intensity testing
    min_floor = 1e-3
    if np.allclose(raw_vals, 0):
        raw_vals[:] = min_floor

    exp_vals = np.exp(raw_vals - np.max(raw_vals))
    probs = exp_vals / (np.sum(exp_vals) + 1e-9)

    # Debug lexicon output
    print("DEBUG: Lexicon sample:", {k: list(v)[:5] for k, v in lexicon.items()})

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
        if re.search(rf"\b{re.escape(intens)}\b", text_lower):
            for k in modified:
                modified[k] *= 1.2

    for deintens in _DEINTENSIFIERS:
        if re.search(rf"\b{re.escape(deintens)}\b", text_lower):
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
    """
    Legacy wrapper updated: returns both valence/arousal summary and emotion distribution.
    """
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
