# ===========================
# core/nlp/__init__.py
# save-state updated 202602201446
# ===========================
"""
Async-only NLP pipeline interface for PeriDocs.

Exposes:
- process_entry_async: full async entry processing (PII, embeddings, repetition, SHA8, emotions)
- tokenize_text, clean_text: minimal text processing
- redact_pii, COMMON_NAMES: PII utilities
- check_crisis_phrases, crisis_notification: crisis detection
- repetition_score: repetition/echo detection
- compute_emotion_profile_async, get_intensifiers, get_deintensifiers: async emotion analysis
- sha8_hash: hashing utilities
"""

from .process_entry import process_entry_async
from .orthography import tokenize_text, clean_text
from .pii import redact_pii, COMMON_NAMES
from .crisis_detector import check_crisis_phrases_async, crisis_notification_async
from .hash_utils import sha8_hash
