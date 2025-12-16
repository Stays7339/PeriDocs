# ==========================================
# core/nlp/text_processing.py
# save-state updated 202512151237
# ==========================================
import re
from typing import List, Tuple, Dict, Any, Optional
import numpy as np
from .fuzzy_utils import get_combined_lexicons, fuzzy_matches_above
from .emotion_analysis import compute_emotion_profile_async
from .embeddings import get_embedding_async
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
    - splits on regex word boundaries
    - returns dict with text only (placeholder for lemma/pos)
    """
    tokens = TOKEN_RE.findall(text)
    return [{"text": t, "lemma": t.lower(), "pos": "X"} for t in tokens]

# ---------------------------------------------------------------------
# Emotion anchor detection (regex + fuzzy matching)
# ---------------------------------------------------------------------
def detect_emotion_tokens(tokens: List[str]) -> List[Tuple[str, str, Optional[int]]]:
    results: List[Tuple[str, str, Optional[int]]] = []
    combined_lexicons = get_combined_lexicons()

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

async def document_features(tokens: List[str], raw_text: Optional[str] = None) -> Dict[str, Any]:
    """
    Generate document-level features combining lexicon + embeddings (async only).

    Parameters:
    - tokens: List of token dicts or strings
    - raw_text: Original text (may contain PII) for embedding/emotion computation.
      Must NOT be persisted to DB or logs.
    """
    base_features = _lexicon_emotion_features([t["text"] if isinstance(t, dict) else t for t in tokens])
    hybrid_features: Dict[str, Any] = {}

    if raw_text:
        # Embeddings/emotion analysis sees full text
        embedding_vector = await get_embedding_async(raw_text)
        hybrid_features["embedding_vector"] = embedding_vector
        emotion_profile = await compute_emotion_profile_async(raw_text)
        hybrid_features["embedding_emotion_distribution"] = emotion_profile
        hybrid_features["valence_arousal_summary"] = {}  # placeholder

    return {**base_features, **hybrid_features}

async def process_text(text: str):
    """
    Full pipeline: clean, tokenize, embeddings, lexicon+embedding emotions.
    Errors propagate; async-only.
    """
    cleaned_text = clean_text(text)
    token_dicts = tokenize_text(cleaned_text)
    token_strings = [t["text"] for t in token_dicts]

    if not cleaned_text:
        embedding_vector = np.zeros((1024,), dtype=np.float32)
        features = {
            "embedding_vector": embedding_vector,
            "embedding_emotion_distribution": {},
            "valence_arousal_summary": {},
            "lexicon_emotion_distribution": {},
        }
        return cleaned_text, token_dicts, token_strings, features

    embedding_vector = await get_embedding_async(cleaned_text)
    features = await document_features(token_dicts, raw_text=cleaned_text)

    return cleaned_text, token_dicts, token_strings, features
