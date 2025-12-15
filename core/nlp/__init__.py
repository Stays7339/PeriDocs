# ===========================
# core/nlp/__init__.py
# save-state updated 202512151407
# ===========================
"""
Async-only NLP pipeline interface for PeriDocs.

Exposes:
- process_entry_async: full async journal entry processing (PII, embeddings, repetition, SHA8, emotions)
- tokenize_text, clean_text: minimal text processing
- redact_pii, COMMON_NAMES: PII utilities
- check_crisis_phrases, crisis_notification: crisis detection
- repetition_score: repetition/echo detection
- compute_emotion_profile_async, get_intensifiers, get_deintensifiers: async emotion analysis
- sha8_hash: hashing utilities
"""

from .process_entry import process_entry_async
from .text_processing import tokenize_text, clean_text
from .pii import redact_pii, COMMON_NAMES
from .crisis import check_crisis_phrases, crisis_notification
from .emotion_analysis import (
    compute_emotion_profile_async,
)
from .hash_utils import sha8_hash
