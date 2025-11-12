"""
core/nlp/__init__.py

This module exposes the main NLP processing pipeline for PeriDocs.
It provides easy access to:
- document_features: full feature extraction for a given text
- process_entry: full processing of a journal entry (PII, NLP, embeddings, SHA8)
- Hooks to submodules for specialized NLP tasks
"""

from .process_entry import process_entry
from .text_processing import tokenize_text, clean_text
from .pii import redact_pii, COMMON_NAMES
from .encryption import encrypt_text, decrypt_text
from .crisis import check_crisis_phrases, crisis_notification
from .embeddings import get_embedding, TOKEN_EMBED_PRECOMPUTE
from .repetition_echo import repetition_score
from .emotion_analysis import emotion_profile
from .hash_utils import sha8_hash
from .sentiment_analysis import compute_sentiment  # now merged with sentiment_label

def document_features(text: str) -> dict:
    """
    Wrapper to extract all NLP features for a given text in a user-friendly format.
    """
    return process_entry(text)
