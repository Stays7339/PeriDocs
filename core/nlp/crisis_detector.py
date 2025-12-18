# ==========================================
# core/nlp/crisis_detector.py
# save-state 202512172138
# ==========================================

from typing import List
from core.nlp.anchors import get_crisis_phrases
from .orthography import token_lemmas

def check_crisis_phrases(text: str, match_threshold: float = 0.9, window_size: int = 10) -> List[str]:
    """
    Crisis phrase detection (lemma-aware, proximity-constrained, partial match).

    Improvements over previous version:
    - Words must appear close together (within `window_size` tokens)
      to reduce false positives in long reflective text.
    - Still lemma-aware and partially matching.
    """
    if not text:
        return []

    tokens = token_lemmas(text)
    tokens_lower = [tok.lower() for tok in tokens]
    crisis_phrases = get_crisis_phrases()
    hits: List[str] = []

    for phrase in crisis_phrases:
        phrase_tokens = [w.lower() for w in phrase.split()]
        if not phrase_tokens:
            continue
        n_phrase = len(phrase_tokens)
        min_required = max(1, int(n_phrase * match_threshold))

        # Slide a window over the text tokens
        for i in range(len(tokens_lower) - window_size + 1):
            window = tokens_lower[i:i+window_size]
            matched_count = sum(tok in window for tok in phrase_tokens)
            if matched_count >= min_required:
                hits.append(phrase)
                break  # only need one valid window

    return hits


def crisis_notification(text: str, match_threshold: float = 0.9, window_size: int = 10) -> str:
    """
    Return standardized warning message if crisis phrases are detected.
    """
    matches = check_crisis_phrases(text, match_threshold=match_threshold, window_size=window_size)
    if not matches:
        return ""
    return (
        "⚠️ Your writing suggests the possibility of emotional or mental health strain. "
        "There are professionals and services outside of PeriDocs equipped to provide guidance."
    )
