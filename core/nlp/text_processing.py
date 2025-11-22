# file: core/nlp/text_processing.py
# Purpose: Minimal spaCy-free text processing and emotion feature extraction for PeriDocs.
# Functions:
#   - clean_text(text)
#   - tokenize_text(text)
#   - detect_emotion_tokens(tokens)
#   - _lexicon_emotion_features(tokens)
#   - document_features(tokens, raw_text=None)
#   - process_text(text)

import re
from typing import List, Tuple, Dict, Any, Optional
from .anchors import _EMOTION_LEXICONS
from .fuzzy_utils import get_combined_lexicons, fuzzy_matches_above
from .emotion_analysis import analyze_emotions, get_emotion_anchors
from .embeddings import get_embedding, get_embedding_async, _deterministic_fallback_vec
import numpy as np
import asyncio

# ---------------------------------------------------------------------
# Regex tokenizer for simple whitespace-based tokenization
# ---------------------------------------------------------------------
TOKEN_RE = re.compile(r"\b\w+(?:['’]\w+)?\b", flags=re.UNICODE)


def clean_text(text: str) -> str:
    """Trim and normalize whitespace. Safe for storage/UI."""
    return re.sub(r"\s+", " ", text.strip())

def tokenize_text(text: str) -> List[Dict[str, Any]]:
    """
    Minimal tokenizer:
    - splits on whitespace / regex
    - returns dict with text only (placeholder for lemma/pos)
    """
    tokens = TOKEN_RE.findall(text)
    return [{"text": t, "lemma": t, "pos": "X", "is_stop": False} for t in tokens]

# ---------------------------------------------------------------------
# Emotion anchor detection (regex + fuzzy matching)
# ---------------------------------------------------------------------
def detect_emotion_tokens(tokens: List[str]) -> List[Tuple[str, str, Optional[int]]]:
    results: List[Tuple[str, str, Optional[int]]] = []
    combined_lexicons = get_combined_lexicons(_EMOTION_LEXICONS)

    for token in tokens:
        token_l = token.lower()
        if len(token_l) < 3:
            continue

        matched = False
        # Exact match
        for emo, lex in combined_lexicons.items():
            if token_l in lex:
                results.append((emo, token, None))
                matched = True
                break
        if matched:
            continue

        # Fuzzy fallback
        for emo, lex in combined_lexicons.items():
            hits = fuzzy_matches_above(token_l, lex, threshold=88)
            if hits:
                best_word, score = hits[0]
                results.append((emo, token, score))
                matched = True
                break

    return results

# ---------------------------------------------------------------------
# Document feature synthesis
# ---------------------------------------------------------------------
def _lexicon_emotion_features(tokens: List[str]) -> Dict[str, Any]:
    emotion_hits = detect_emotion_tokens(tokens)
    hit_counts: Dict[str, int] = {}
    for emo, tok, score in emotion_hits:
        hit_counts.setdefault(emo, 0)
        hit_counts[emo] += 1

    total_hits = sum(hit_counts.values())
    normalized_hits = {emo: (count / total_hits if total_hits else 0.0) for emo, count in hit_counts.items()}

    return {
        "token_count": len(tokens),
        "emotion_anchor_hits": normalized_hits,
        "raw_emotion_hits": emotion_hits,
    }

def document_features(
    tokens: List[str],
    raw_text: Optional[str] = None,
    crisis: bool = False
) -> Dict[str, Any]:
    """
    Generate document-level features combining lexicon + embeddings (if raw_text provided).

    Parameters:
    - tokens: List of token dicts or strings
    - raw_text: Original text (may contain PII) for embedding/emotion computation.
      Must NOT be persisted to DB or logs.
    - crisis: If True, indicates entry is crisis flagged; computation is ephemeral only.
    """
    base_features = _lexicon_emotion_features(tokens)
    hybrid_features = {}

    if raw_text:
        # Embeddings/emotion analysis sees full text (including PII) but memory-only
        text_for_computation = raw_text  # temporary, not stored
        try:
            emotion_embedding_data = analyze_emotions(text_for_computation)
            hybrid_features["embedding_emotion_distribution"] = emotion_embedding_data.get("emotion_distribution", {})
            hybrid_features["valence_arousal_summary"] = emotion_embedding_data.get("valence_arousal_summary", {})
        except Exception as e:
            hybrid_features["embedding_emotion_distribution"] = {}
            hybrid_features["valence_arousal_summary"] = {}
            hybrid_features["error"] = f"emotion_analysis_failed: {e}"

    return {**base_features, **hybrid_features}

# Define ALL_EMOTION_KEYS dynamically from current anchors
ALL_EMOTION_KEYS = list(get_emotion_anchors().keys())

def compute_emotions_from_embedding(embedding_vector: np.ndarray) -> dict:
    """
    Minimal deterministic fallback: uniform emotion distribution from embedding vector.
    """
    return {k: 1.0 / len(ALL_EMOTION_KEYS) for k in ALL_EMOTION_KEYS}

def process_text(text: str):
    """
    Full pipeline: clean, tokenize, embeddings, lexicon+embedding emotions, valence/arousal.
    Guarantees:
      - embedding_vector is never None for non-empty text
      - emotion_distribution is always non-empty
      - valence/arousal summary is always present
    """

    cleaned_text = text.strip()
    token_dicts = [{"text": t, "lemma": t.lower(), "pos": "X"} for t in cleaned_text.split()]
    token_strings = [t["text"] for t in token_dicts]

    features: dict = {}

    if not cleaned_text:
        # fallback for empty text
        features["embedding_vector"] = np.zeros((768,), dtype=np.float32)
        features["embedding_emotion_distribution"] = {k: 0.0 for k in ALL_EMOTION_KEYS}
        features["valence_arousal_summary"] = {}
        features["lexicon_emotion_distribution"] = {k: 0.0 for k in ALL_EMOTION_KEYS}
        return cleaned_text, token_dicts, token_strings, features

    # ---------------- EMBEDDING ----------------
    try:
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                embedding_vector = get_embedding(cleaned_text)
            else:
                embedding_vector = asyncio.run(get_embedding_async(cleaned_text))
        except RuntimeError:
            embedding_vector = get_embedding(cleaned_text)

        if embedding_vector is None or np.all(embedding_vector == 0.0):
            embedding_vector = _deterministic_fallback_vec(cleaned_text)
        features["embedding_vector"] = embedding_vector

    except Exception:
        embedding_vector = _deterministic_fallback_vec(cleaned_text)
        features["embedding_vector"] = embedding_vector

    # ---------------- EMOTIONS ----------------
    try:
        # Lexicon + intensity adjusted emotions
        emotion_data = analyze_emotions(cleaned_text)
        features["embedding_emotion_distribution"] = emotion_data.get("emotion_distribution", compute_emotions_from_embedding(embedding_vector))
        features["valence_arousal_summary"] = emotion_data.get("valence_arousal_summary", {})

        # Optional: lexicon-only distribution (pure anchor hits)
        lexicon_hits = detect_emotion_tokens(token_strings)
        lexicon_counts = {k: 0 for k in ALL_EMOTION_KEYS}
        for emo, _, _ in lexicon_hits:
            if emo in lexicon_counts:
                lexicon_counts[emo] += 1
        total = sum(lexicon_counts.values())
        if total > 0:
            features["lexicon_emotion_distribution"] = {k: v / total for k, v in lexicon_counts.items()}
        else:
            features["lexicon_emotion_distribution"] = {k: 0.0 for k in ALL_EMOTION_KEYS}

    except Exception:
        features["embedding_emotion_distribution"] = compute_emotions_from_embedding(embedding_vector)
        features["valence_arousal_summary"] = {}
        features["lexicon_emotion_distribution"] = {k: 0.0 for k in ALL_EMOTION_KEYS}

    return cleaned_text, token_dicts, token_strings, features

