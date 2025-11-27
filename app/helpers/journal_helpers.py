from datetime import datetime
from typing import Dict, Optional
import numpy as np
from core.nlp.process_entry import normalize_vector

def sentiment_label(score: float) -> str:
    if score > 0.05:
        return "positive"
    elif score < -0.05:
        return "negative"
    return "neutral"

def prune_entry(entry: Dict, keep_embeddings: bool = False) -> Dict:
    """Safe storage version of a journal entry"""
    embedding = entry.get("embedding") if keep_embeddings else None
    if embedding is not None and isinstance(embedding, np.ndarray):
        embedding = embedding.tolist()

    pruned = {
        "id": entry.get("sha8"),
        "safe_text": entry.get("safe_text"),
        "timestamp": datetime.utcnow().isoformat(),
        "nlp": {
            "sentiment": float(entry.get("sentiment", 0.0)),
            "emotions": entry.get("emotions") or {},
            "weighted_emotion_distribution": entry.get("weighted_emotion_distribution") or {},
            "entities": entry.get("entities") or [],
            "embedding": embedding,
            "crisis_flag": entry.get("crisis_flag", False),
            "summary": entry.get("summary")
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
