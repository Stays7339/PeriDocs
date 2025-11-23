"""
core/nlp/__init__.py save-state updated 202511231610 (date and time formatted as follows: YYYYMMDDhhmm)

Main NLP pipeline interface for PeriDocs.

Provides:
- document_features: full feature extraction for a given text (sync wrapper)
- process_entry: full processing of a journal entry (PII, embeddings, repetition, SHA8)
- Hooks to submodules for specialized NLP tasks
- Backward-compatible sentiment computation via emotion_analysis
"""

from .process_entry import process_entry  # sync wrapper
from .text_processing import tokenize_text, clean_text
from .pii import redact_pii, COMMON_NAMES
from .encryption import encrypt_text, decrypt_text
from .crisis import check_crisis_phrases, crisis_notification
from .embeddings import get_embedding, TOKEN_EMBED_PRECOMPUTE
from .repetition_echo import repetition_score
from .emotion_analysis import (
    emotion_profile,
    compute_sentiment_from_profile,
    analyze_emotions,
    get_emotion_anchors,
    get_intensifiers,
    get_deintensifiers,
)
from .hash_utils import sha8_hash

# -------------------------------
# Backward-compatible alias
# -------------------------------
compute_sentiment = compute_sentiment_from_profile

# -------------------------------
# Wrapper for full NLP features
# -------------------------------
def document_features(text: str) -> dict:
    """
    Wrapper to extract all NLP features for a given text in a user-friendly format.
    Calls the sync wrapper in process_entry.py.
    """
    return process_entry(text)
