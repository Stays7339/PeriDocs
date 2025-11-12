"""
core/nlp/sentiment_analysis.py

Computes polarity and maps sentiment scores to human-readable buckets.
Uses emotion_profile (valence/arousal) to derive a continuous polarity score.
"""

from typing import Dict, Any
from math import tanh
from core.nlp.emotion_analysis import emotion_profile

# Simple thresholds for textual labels
_POSITIVE_THRESHOLD = 0.05
_NEGATIVE_THRESHOLD = -0.05

def compute_sentiment(text: str) -> Dict[str, Any]:
    """
    Returns sentiment analysis dictionary for a given text.
    Uses emotion_profile's valence/arousal to compute normalized polarity in -1..1.
    Maps polarity to label in a single consistent API.
    """
    ep = emotion_profile(text)
    valence = float(ep.get("valence", 0.0))
    arousal = float(ep.get("arousal", 0.0)) or 1.0

    # Use tanh to squash valence/arousal into -1..1 smoothly; stronger arousal increases magnitude
    polarity = tanh(valence / max(1.0, arousal))

    # subjectivity placeholder
    subjectivity = 0.0

    # map to label
    if polarity >= _POSITIVE_THRESHOLD:
        label = "positive"
    elif polarity <= _NEGATIVE_THRESHOLD:
        label = "negative"
    else:
        label = "neutral"

    return {
        "polarity": float(polarity),
        "subjectivity": float(subjectivity),
        "label": label,
        "source": "emotion-profile"
    }

