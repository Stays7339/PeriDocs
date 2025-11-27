"""
core/nlp/emotion_analysis.py 
save-state updated 202511241720 (updated for display-ready emotion percentages, raw_text, and sorted output)

Emotion analysis module for PeriDocs.

Handles:
- Numeric weighting, normalization, and summary of emotion distributions.
- Valence/arousal mapping.
- Modified intensity scores using simplified intensifiers/deintensifiers.
- Lexicon constants are imported from anchors.py and combined with dynamic lexicons.
- Normalization of emotion calculations only immediately before use, not between math steps.

Backward compatibility: compute_sentiment_from_profile() replaces sentiment_analysis.py.
"""

import asyncio
import hashlib
import re
from math import tanh
from typing import Dict, Set, Optional

import numpy as np
from core.nlp.embeddings import get_embedding, batch_embeddings_async
from core.nlp.anchors import get_emotion_anchor
from core.nlp.fuzzy_utils import get_combined_lexicons

# -------------------------------
# INTENSIFIERS & DEINTENSIFIERS
# -------------------------------
_INTENSIFIERS: Set[str] = {"very", "extremely", "really", "super", "ultra"}
_DEINTENSIFIERS: Set[str] = {"slightly", "somewhat", "a bit", "barely"}

_INTENSIFIER_REGEX = re.compile(
    r"\b(" + "|".join(re.escape(i) for i in _INTENSIFIERS) + r")\b['’.,!?]?", re.IGNORECASE
)
_DEINTENSIFIER_REGEX = re.compile(
    r"\b(" + "|".join(re.escape(d) for d in _DEINTENSIFIERS) + r")\b['’.,!?]?", re.IGNORECASE
)

# -------------------------------
# STATIC EMOTION ANCHORS
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
# LEXICON EMBEDDING CACHE
# -------------------------------
_lexicon_embedding_cache: Dict[str, np.ndarray] = {}
_deterministic_fallback_cache: Dict[str, np.ndarray] = {}

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

def _deterministic_fallback_vec(raw_text: str, dim: int = 768) -> np.ndarray:
    if raw_text in _deterministic_fallback_cache:
        return _deterministic_fallback_cache[raw_text]
    h = hashlib.sha256(raw_text.encode("utf-8")).digest()
    rng = np.frombuffer(h * ((dim // len(h)) + 1), dtype=np.uint8)[:dim].astype(np.float32)
    rng -= np.mean(rng)
    norm = np.linalg.norm(rng)
    if norm == 0:
        rng = np.ones((dim,), dtype=np.float32)
        norm = float(np.linalg.norm(rng))
    vec = (rng / norm).astype(np.float32)
    _deterministic_fallback_cache[raw_text] = vec
    return vec

# -------------------------------
# ASYNC EMBEDDINGS
# -------------------------------
async def get_embedding_async(raw_text: str, model_name: str = "all-roberta-large-v1") -> np.ndarray:
    return get_embedding(raw_text, model_name)

async def _get_lexicon_embeddings_async(lexicon: Dict[str, Set[str]]) -> Dict[str, np.ndarray]:
    embeddings = {}
    all_words = []
    word_to_emo = {}

    for emo, words in lexicon.items():
        for w in words:
            lw = w.lower()
            if lw not in _lexicon_embedding_cache:
                all_words.append(lw)
            word_to_emo[lw] = emo

    if all_words:
        new_embs = await batch_embeddings_async(all_words)
        for w, vec in zip(all_words, new_embs):
            _lexicon_embedding_cache[w] = vec

    for emo, words in lexicon.items():
        vecs = [_lexicon_embedding_cache[w.lower()] for w in words if w.lower() in _lexicon_embedding_cache]
        embeddings[emo] = np.stack(vecs) if vecs else np.zeros((0, 768), dtype=np.float32)

    return embeddings

# -------------------------------
# EMOTION PROFILE COMPUTATION
# -------------------------------
async def compute_emotion_profile_async(
    raw_text: str,
    emotion_analysis: Optional[Dict[str, Set[str]]] = None,
    model_name: str = "all-roberta-large-v1"
) -> Dict[str, float]:
    combined_lexicons = get_combined_lexicons(_EMOTION_LEXICONS)
    lexicon = emotion_analysis or combined_lexicons
    emotions = list(lexicon.keys())

    if not raw_text.strip():
        return {emotion: 0.0 for emotion in emotions}

    try:
        text_vec = await get_embedding_async(raw_text, model_name)
        lexicon_vecs = await _get_lexicon_embeddings_async(lexicon)
    except Exception as e:
        raise RuntimeError(f"Embedding computation failed: {e}")

    scores = {}
    for emo, vectors in lexicon_vecs.items():
        if vectors.size == 0:
            scores[emo] = 0.0
            continue
        similarities = np.dot(vectors, text_vec) / (np.linalg.norm(vectors, axis=1) * np.linalg.norm(text_vec) + 1e-9)
        scores[emo] = float(np.mean(np.clip(similarities, -1, 1)))

    # Deterministic softmax to produce a probability distribution
    raw_vals = np.array(list(scores.values()), dtype=float)
    raw_vals = np.where(np.isnan(raw_vals) | (raw_vals == 0), 1e-3, raw_vals)
    tau = 0.85
    centered = (raw_vals - np.max(raw_vals)) / max(tau, 1e-9)
    tie_break = np.array([hash(e) % 10_000 for e in emotions], dtype=float) * 1e-12
    centered += tie_break
    exp_vals = np.exp(centered)
    probs = exp_vals / (np.sum(exp_vals) + 1e-9)
    return dict(zip(emotions, probs))

# -------------------------------
# VALENCE & AROUSAL SUMMARY
# -------------------------------
def summarize_valence_arousal(emotion_profile: Dict[str, float]) -> Dict[str, float]:
    valence_map = {"joy": 1.0, "trust": 0.7, "anticipation": 0.5,
                   "anger": -0.8, "disgust": -0.9, "sadness": -1.0,
                   "fear": -0.7, "surprise": 0.2}
    arousal_map = {"joy": 0.6, "trust": 0.3, "anticipation": 0.8,
                   "anger": 0.9, "disgust": 0.7, "sadness": 0.2,
                   "fear": 0.8, "surprise": 1.0}

    valence = sum(emotion_profile.get(e, 0) * valence_map.get(e, 0) for e in emotion_profile)
    arousal = sum(emotion_profile.get(e, 0) * arousal_map.get(e, 0) for e in emotion_profile)

    return {"valence": sigmoid(valence * 3), "arousal": np.clip(arousal, 1e-6, 1.0)}

# -------------------------------
# INTENSITY MODIFIERS
# -------------------------------
def apply_intensity_modifiers(tokens: list, base_profile: Dict[str, float], lexicon: Dict[str, set]) -> Dict[str, float]:
    if not tokens:
        return base_profile.copy()
    modified = base_profile.copy()
    token_count = len(tokens)

    for i, token in enumerate(tokens):
        token_l = token.lower()
        if token_l in _INTENSIFIERS or token_l in _DEINTENSIFIERS:
            factor = 1.2 if token_l in _INTENSIFIERS else 0.8
            for j in [i - 1, i + 1]:
                if 0 <= j < token_count:
                    neigh = tokens[j].lower()
                    for emo, words in lexicon.items():
                        if neigh in words:
                            modified[emo] *= factor
    return modified

# -------------------------------
# EMOTION DISPLAY FORMAT
# -------------------------------
def format_emotion_distribution(dist: dict) -> str:
    """Convert raw probabilities to percentages, sort descending, return display string."""
    percent_dist = {emo: round(prob * 100, 1) for emo, prob in dist.items()}
    sorted_items = sorted(percent_dist.items(), key=lambda x: x[1], reverse=True)
    return ", ".join(f"{emo}: {val}%" for emo, val in sorted_items)

# -------------------------------
# MASTER ASYNC PIPELINE
# -------------------------------
async def analyze_emotions_async(raw_text: str) -> Dict[str, Dict[str, float]]:
    TOKEN_RE = re.compile(r"\b\w+(?:['’]\w+)?\b", flags=re.UNICODE)
    tokens = TOKEN_RE.findall(raw_text)
    lexicon = get_combined_lexicons(_EMOTION_LEXICONS)
    base_profile = await compute_emotion_profile_async(raw_text, lexicon)

    adjusted_profile = apply_intensity_modifiers(tokens, base_profile, lexicon)

    # Weighted combination: lexicon-adjusted vs embedding-base
    lex_weight, emb_weight = 0.7, 0.3
    combined_profile = {emo: lex_weight * adjusted_profile.get(emo, 0.0) + emb_weight * base_profile.get(emo, 0.0)
                        for emo in base_profile}

    # Convert to percentages and sort descending
    percent_dist = {emo: round(prob * 100, 2) for emo, prob in combined_profile.items()}
    sorted_percent_dist = dict(sorted(percent_dist.items(), key=lambda x: x[1], reverse=True))

    summary = summarize_valence_arousal(combined_profile)

    return {
        "emotion_distribution": sorted_percent_dist,
        "emotion_distribution_str": format_emotion_distribution(combined_profile),
        "valence_arousal_summary": summary
    }

def normalize_emotion_profile(emotions: dict) -> dict:
    """
    Normalize and flatten the emotion structure so downstream code
    always receives a simple flat dict: {emotion: float}.
    Updated 20251126:
    - Supports new PeriDocs structure that uses 'emotion_distribution'
      instead of legacy 'weighted_emotion_distribution' or
      'embedding_emotion_distribution'.
    """

    # NEW: Prefer the modern PeriDocs structure.
    if isinstance(emotions, dict):
        if "emotion_distribution" in emotions and isinstance(emotions["emotion_distribution"], dict):
            profile = emotions["emotion_distribution"]

        # Legacy support (unchanged)
        else:
            weighted = emotions.get("weighted_emotion_distribution")
            if isinstance(weighted, dict) and weighted:
                profile = weighted
            else:
                embedding = emotions.get("embedding_emotion_distribution")
                if isinstance(embedding, dict) and embedding:
                    profile = embedding
                else:
                    # If it's already a flat dict of floats, use it directly.
                    profile = emotions
    else:
        return {}

    # Ensure profile is flat numeric
    numeric_items = {k: v for k, v in profile.items() if isinstance(v, (int, float))}
    if not numeric_items:
        return {}

    total = sum(numeric_items.values())
    if total > 0:
        normalized = {k: v / total for k, v in numeric_items.items()}
    else:
        normalized = {k: 0.0 for k in numeric_items}

    return normalized

# -------------------------------
# SYNC FACADES & BACKWARD COMPATIBILITY
# -------------------------------
def analyze_emotions(raw_text: str) -> Dict[str, Dict[str, float]]:
    import nest_asyncio
    nest_asyncio.apply()
    return asyncio.run(analyze_emotions_async(raw_text))

def emotion_profile(raw_text: str) -> Dict[str, Dict[str, float]]:
    return analyze_emotions(raw_text)

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

def get_emotion_anchors() -> Dict[str, Set[str]]:
    return _EMOTION_LEXICONS

def get_intensifiers() -> Set[str]:
    return _INTENSIFIERS

def get_deintensifiers() -> Set[str]:
    return _DEINTENSIFIERS
