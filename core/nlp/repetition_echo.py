"""
core/nlp/repetition_echo.py
"""
import logging
from collections import Counter

def repetition_score(text: str, window: int = 5) -> float:
    """
    Compute a repetition/echo weighting score based on n-gram frequency.
    """
    try:
        words = text.split()
        if len(words) < 2:
            return 0.0
        ngrams = zip(*[words[i:] for i in range(window)])
        ngram_counts = Counter(ngrams)
        total_ngrams = sum(ngram_counts.values())
        repeated = sum(count-1 for count in ngram_counts.values() if count > 1)
        return repeated / total_ngrams if total_ngrams else 0.0
    except Exception as e:
        logging.error(f"Repetition scoring failed: {e}")
        return 0.0
