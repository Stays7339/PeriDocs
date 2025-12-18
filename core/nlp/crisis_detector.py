# ==========================================
# core/nlp/crisis_detector.py
# updated 202512171403
# ==========================================

from typing import List
from core.nlp.anchors import get_crisis_phrases
from .orthography import token_lemmas

def check_crisis_phrases(text: str, match_threshold: float = 0.9) -> List[str]:
    """
    Crisis phrase detection (lemma-aware, order-flexible, partial match).

    This function identifies crisis-related content while being sensitive
    to different word forms (e.g., "kill", "killed", "killing"). For
    multi-word phrases, it flags a match if a configurable proportion
    of the phrase words appear in the text (default 90%), regardless of
    order or intervening words.

    This reduces false negatives caused by verb tenses or word reordering,
    while maintaining a strong ethical and legal duty to flag potential harm.

    Example: crisis phrase = "kill myself now"

    Text: "I want to kill and hurt myself" → matches, because "kill" and "myself"
    appear, even if "now" is missing, as long as threshold is met.

    Text: "I killed someone" → "kill" lemma matches "killed".

    Pros: catches more varied expressions of crisis.
    Cons: may generate false positives if words appear separately but not in
          the intended context.

    Parameters:
    -----------
    text : str
        User input text.
    match_threshold : float
        Fraction of phrase words that must appear to trigger a match (0 < threshold ≤ 1).

    Returns:
    --------
    List[str]
        List of crisis phrases detected in the text.
    """
    if not text:
        return []

    text_lemmas = set(token_lemmas(text))  # O(1) lookup
    crisis_phrases = get_crisis_phrases()
    hits: List[str] = []

    for phrase in crisis_phrases:
        phrase_tokens = [w.lower() for w in phrase.split()]
        if not phrase_tokens:
            continue

        # Count how many phrase words appear in text lemmas
        matched_count = sum(tok in text_lemmas for tok in phrase_tokens)
        if matched_count / len(phrase_tokens) >= match_threshold:
            hits.append(phrase)

    return hits


def crisis_notification(text: str, match_threshold: float = 0.9) -> str:
    """
    Return standardized warning message if crisis phrases are detected.
    Fully lemma-aware and partially matching.

    Parameters:
    -----------
    text : str
        User input text.
    match_threshold : float
        Fraction of phrase words required to trigger a match.

    Returns:
    --------
    str
        Warning message, empty string if no crisis phrases detected.
    """
    matches = check_crisis_phrases(text, match_threshold=match_threshold)
    if not matches:
        return ""
    return (
        "⚠️ Your writing suggests the possibility of emotional or mental health strain. "
        "There are professionals and services outside of PeriDocs equipped to provide guidance."
    )
