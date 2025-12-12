"""
PeriDocs-code/core/nlp/text_processing.py
Save-state: 202512121204
Embeddings-only text processing for PeriDocs.
- Async everywhere
- Embedding-driven emotion extraction
- No sentiment, no valence/arousal
"""

import asyncio
import re
from typing import List, Dict, Any, Optional
import numpy as np
from .embeddings import get_embedding_async, _deterministic_fallback_vec
from .emotion_model import compute_emotion_distribution
from .emotion_analysis import normalize_emotion_profile

TOKEN_RE = re.compile(r"\b\w+(?:['’]\w+)?\b", flags=re.UNICODE)
_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]?")

def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())

def tokenize_text(text: str) -> List[Dict[str, Any]]:
    tokens = TOKEN_RE.findall(text)
    return [{"text": t, "lemma": t.lower(), "pos": "X"} for t in tokens]

def split_sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_RE.findall(text) if s.strip()]

def compute_emotions_from_embedding(embedding_vector: np.ndarray, approved_labels: Optional[List[str]] = None) -> Dict[str, float]:
    if not approved_labels:
        return {}
    n = len(approved_labels)
    return {emo: 1.0 / n for emo in approved_labels}

async def document_features_async(tokens: List[str], raw_text: Optional[str] = None) -> Dict[str, Any]:
    features: Dict[str, Any] = {}
    cleaned_text = (raw_text or "").strip()
    if not cleaned_text:
        features["embedding_vector"] = np.zeros((1024,), dtype=np.float32)
        features["embedding_emotion_distribution"] = {}
        return features

    try:
        embedding_vector = await get_embedding_async(cleaned_text)
        if embedding_vector is None or np.all(embedding_vector == 0.0):
            embedding_vector = _deterministic_fallback_vec(cleaned_text)
    except Exception:
        embedding_vector = _deterministic_fallback_vec(cleaned_text)
    features["embedding_vector"] = embedding_vector

    try:
        emotion_data = await compute_emotion_distribution(cleaned_text)
        if not emotion_data:
            emotion_data = compute_emotions_from_embedding(embedding_vector, approved_labels=None)
        features["embedding_emotion_distribution"] = normalize_emotion_profile(emotion_data)
    except Exception:
        features["embedding_emotion_distribution"] = compute_emotions_from_embedding(embedding_vector, approved_labels=None)

    return features

async def process_text_async(text: str):
    cleaned_text = clean_text(text)
    token_dicts = tokenize_text(cleaned_text)
    token_strings = [t["text"] for t in token_dicts]
    if not cleaned_text:
        return cleaned_text, token_dicts, token_strings, {"embedding_vector": np.zeros((1024,), dtype=np.float32), "embedding_emotion_distribution": {}}
    features = await document_features_async(token_dicts, raw_text=cleaned_text)
    return cleaned_text, token_dicts, token_strings, features
