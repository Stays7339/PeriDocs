"""
core/nlp/process_entry.py

Full NLP processing pipeline for a single journal entry.
Handles cleaning, PII redaction, embeddings, sentiment, emotion,
repetition scoring, hashing, crisis detection, and encryption.
"""

from typing import Dict
import numpy as np

from .text_processing import clean_text, tokenize_text
from .pii import redact_pii
from .embeddings import get_embedding
from .repetition_echo import repetition_score
from .emotion_analysis import analyze_emotions, compute_sentiment_from_profile
from .hash_utils import sha8_hash
from .encryption import encrypt_text
from .crisis import check_crisis_phrases

def _normalize_distribution(dist: Dict[str, float]) -> Dict[str, float]:
    total = sum(abs(v) for v in dist.values())
    if total == 0:
        return {k: 0.0 for k in dist}
    return {k: round(v / total, 4) for k, v in dist.items()}

def process_entry(text: str) -> Dict:
    cleaned_text = clean_text(text)
    embedding_vector = np.array(get_embedding(cleaned_text))
    embedding_mean = float(embedding_vector.mean()) if embedding_vector.size > 0 else 0.0
    redacted_text = redact_pii(cleaned_text)

    # --- Emotion & Sentiment
    emotion_data = analyze_emotions(redacted_text)
    emotions = emotion_data["emotion_distribution"]
    summary = emotion_data["valence_arousal_summary"]
    sentiment = compute_sentiment_from_profile(summary)

    repetition = repetition_score(redacted_text)
    weighted_emotions = {emo: val * (1 + abs(sentiment.get("polarity", 0.0))) for emo, val in emotions.items()}
    weighted_emotions = _normalize_distribution(weighted_emotions)
    primary_emotion = max(weighted_emotions, key=weighted_emotions.get) if weighted_emotions else None

    entry_hash = sha8_hash(redacted_text)
    crisis_flags = check_crisis_phrases(redacted_text)
    encrypted_text = encrypt_text(cleaned_text)

    return {
        "text_encrypted": encrypted_text,
        "embedding": embedding_vector,
        "embedding_mean": embedding_mean,
        "sentiment": sentiment,
        "emotion": emotions,
        "weighted_emotion_distribution": weighted_emotions,
        "summary": {
            "primary_emotion": primary_emotion,
            "sentiment_label": sentiment.get("label"),
            "intensity": round(sum(weighted_emotions.values()), 3),
        },
        "repetition": repetition,
        "sha8": entry_hash,
        "crisis_flags": crisis_flags,
    }
