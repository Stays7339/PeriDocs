from datetime import datetime
from typing import Dict, Optional
import numpy as np
from core.nlp.process_entry import normalize_vector
from core.nlp.emotion_analysis import compute_sentiment_from_valence_arousal

def sentiment_label(score: float) -> str:
    if score > 0.05:
        return "positive"
    elif score < -0.05:
        return "negative"
    return "neutral"

def prune_entry(entry: Dict, keep_embeddings: bool = False) -> Dict:
    """
    Prepare a safe storage version of a journal entry.

    This function:
    - Converts embeddings to lists if requested.
    - Extracts NLP results (emotion distribution, valence/arousal, polarity, sentiment label).
    - Computes sentiment label from valence/arousal if not already present.
    - Preserves only essential fields for storage.

    Storage Schema:
    ---------------
    nlp: {
        sentiment: {
            polarity: float,
            label: str,
            valence: float,
            arousal: float
        },
        emotions: dict,                   # raw emotion probabilities
        weighted_emotion_distribution: dict,
        dominant_emotion: str,
        entities: list,
        embedding: list or None,
        crisis_flag: bool,
        summary: str
    }

    Notes on terms:
    ----------------
    - Valence: Pleasantness/unpleasantness of emotion, mapped from emotion distribution.
    - Arousal: Intensity of emotion; high = excited/strong, low = calm.
    - Polarity: Numeric summary of valence/arousal in [-1,1].
    - Sentiment: Human-readable label derived from polarity ('positive', 'neutral', 'negative').
    """
    embedding = entry.get("embedding") if keep_embeddings else None
    if embedding is not None and isinstance(embedding, np.ndarray):
        embedding = embedding.tolist()

    nlp = entry.get("nlp", {})
    va_summary = nlp.get("valence_arousal_summary", {})
    valence = float(va_summary.get("valence", 0.0))
    arousal = float(va_summary.get("arousal", 1.0))

    sentiment = compute_sentiment_from_valence_arousal(valence, arousal)

    # --------- SOLUTION: Correctly fetch weighted_emotion_distribution and dominant_emotion ---------
    weighted_emotions = entry.get("weighted_emotion_distribution") or {}
    if not weighted_emotions and "emotions" in entry and "weighted" in entry["emotions"]:
        weighted_emotions = entry["emotions"]["weighted"]

    dominant_emotion = entry.get("dominant_emotion")
    if not dominant_emotion:
        dominant_emotion = max(weighted_emotions, key=weighted_emotions.get) if weighted_emotions else None
    # ---------------------------------------------------------------------------------------------

    pruned = {
        "id": entry.get("sha8"),
        "safe_text": entry.get("safe_text"),
        "timestamp": datetime.utcnow().isoformat(),
        "nlp": {
            "sentiment": sentiment,
            "emotions": entry.get("emotions") or {},
            "weighted_emotion_distribution": weighted_emotions,
            "dominant_emotion": dominant_emotion,
            "entities": nlp.get("entities") or [],
            "embedding": embedding,
            "crisis_flag": nlp.get("crisis_flag", False),
            "summary": nlp.get("summary")
        }
    }
    return pruned

def safe_normalize_embedding(vec: Optional[np.ndarray]) -> Optional[list]:
    """Normalize vector safely; return list or None"""
    if vec is None:
        return None
    try:
        norm = normalize_vector(vec)
        if isinstance(norm, np.ndarray):
            norm = norm.tolist()
        return norm
    except Exception:
        return vec.tolist() if isinstance(vec, np.ndarray) else vec
