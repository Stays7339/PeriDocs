"""
============ core/nlp/text_processing.py =============

Hybrid version — merges spaCy dependency parsing and linguistic metadata
with fuzzy emotion anchor detection and combined lexicon integration.

Provides:
- Text cleaning and normalization
- spaCy-based tokenization with lemma/POS/stopword metadata
- Emotion anchor detection (exact + fuzzy)
- Rich document features (emotion anchors, token counts, hybrid emotion embeddings)
- Backward-compatible process_text() function

Dependencies:
    pip install spacy rapidfuzz
    python -m spacy download en_core_web_sm
"""

import re
import spacy
from typing import List, Tuple, Dict, Any, Optional
from core.nlp.anchors import _EMOTION_LEXICONS
from core.nlp.fuzzy_utils import get_combined_lexicons, fuzzy_matches_above
from core.nlp.emotion_analysis import analyze_emotions

# ---------------------------------------------------------------------
# spaCy model setup (with robust fallback warning)
# ---------------------------------------------------------------------
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    raise RuntimeError(
        "spaCy model 'en_core_web_sm' not found. "
        "Install it with: python -m spacy download en_core_web_sm"
    )

# Ensure sentence segmentation
if "sentencizer" not in nlp.pipe_names:
    nlp.add_pipe("sentencizer")

# ---------------------------------------------------------------------
# Regex tokenizer (optional hybrid use)
# ---------------------------------------------------------------------
TOKEN_RE = re.compile(r"\b\w[\w']*\b", flags=re.UNICODE)

# ---------------------------------------------------------------------
# Cleaning utilities
# ---------------------------------------------------------------------
def clean_text(text: str) -> str:
    """Trim and normalize whitespace."""
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text

# ---------------------------------------------------------------------
# spaCy tokenization with linguistic metadata
# ---------------------------------------------------------------------
def tokenize_text(text: str) -> List[Dict[str, Any]]:
    """
    Tokenize text using spaCy and return list of token metadata dicts.

    Returns:
        List[Dict[str, Any]] where each dict contains:
            - text
            - lemma
            - pos
            - is_stop
    """
    doc = nlp(text)
    tokens = []
    for token in doc:
        tokens.append({
            "text": token.text,
            "lemma": token.lemma_,
            "pos": token.pos_,
            "is_stop": token.is_stop,
        })
    return tokens

# ---------------------------------------------------------------------
# Emotion anchor detection (exact + fuzzy)
# ---------------------------------------------------------------------
def detect_emotion_tokens(tokens: List[str]) -> List[Tuple[str, str, Optional[int]]]:
    """
    Detect tokens matching emotion anchors.
    Returns list of tuples (emotion_category, matched_token, match_score_or_None).

    Uses:
        - Exact match first
        - Fuzzy match fallback (via rapidfuzz)
    """
    results: List[Tuple[str, str, Optional[int]]] = []
    combined_lexicons = get_combined_lexicons(_EMOTION_LEXICONS)

    for token in tokens:
        token_l = token.lower()
        if len(token_l) < 3:
            continue  # skip short tokens for performance

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
# Document feature synthesis (lexicon-based)
# ---------------------------------------------------------------------
def _lexicon_emotion_features(tokens: List[str]) -> Dict[str, Any]:
    emotion_hits = detect_emotion_tokens(tokens)
    hit_counts: Dict[str, int] = {}
    for emo, tok, score in emotion_hits:
        hit_counts.setdefault(emo, 0)
        hit_counts[emo] += 1

    total_hits = sum(hit_counts.values())
    normalized_hits = {
        emo: (count / total_hits) if total_hits > 0 else 0.0
        for emo, count in hit_counts.items()
    }

    return {
        "token_count": len(tokens),
        "emotion_anchor_hits": normalized_hits,
        "raw_emotion_hits": emotion_hits,
    }

# ---------------------------------------------------------------------
# Hybrid document feature synthesis
# ---------------------------------------------------------------------
def document_features(tokens: List[str], raw_text: Optional[str] = None) -> Dict[str, Any]:
    """
    Generate document-level features combining:
      - Emotion anchor distributions
      - Token statistics
      - Optional embedding-based emotion analysis (if raw_text provided)
    """
    base_features = _lexicon_emotion_features(tokens)

    hybrid_features = {}
    if raw_text:
        try:
            emotion_embedding_data = analyze_emotions(raw_text)
            hybrid_features["embedding_emotion_distribution"] = (
                emotion_embedding_data.get("emotion_distribution", {})
            )
            hybrid_features["valence_arousal_summary"] = (
                emotion_embedding_data.get("valence_arousal_summary", {})
            )
        except Exception as e:
            hybrid_features["embedding_emotion_distribution"] = {}
            hybrid_features["valence_arousal_summary"] = {}
            hybrid_features["error"] = f"emotion_analysis_failed: {e}"

    merged = {**base_features, **hybrid_features}
    return merged

# ---------------------------------------------------------------------
# Unified entry point: clean, tokenize, and analyze
# ---------------------------------------------------------------------
def process_text(text: str) -> Tuple[
    str, "spacy.tokens.Doc", List[Dict[str, Any]], List[str], Dict[str, Any]
]:
    """
    End-to-end text processing pipeline:
    - Cleans text
    - Creates spaCy Doc
    - Extracts token metadata and plain tokens
    - Runs emotion anchor detection + hybrid feature synthesis

    Returns:
        (
            cleaned_text,
            doc,
            token_dicts,
            token_strings,
            doc_features
        )
    """
    cleaned = clean_text(text)
    doc = nlp(cleaned)
    token_dicts = tokenize_text(cleaned)
    token_strings = [t["text"] for t in token_dicts]
    features = document_features(token_strings, raw_text=cleaned)

    return cleaned, doc, token_dicts, token_strings, features
