"""
# core/nlp/pii.py
Save-state 202602201448

PeriDocs PII Redaction Module
-----------------------------

Purpose:
    Centralized handling of Personally Identifiable Information (PII) detection
    and redaction across the system. Designed for safe storage of entries
    and other textual content while maintaining privacy.

Features:
---------
1. Redacts:
   - Emails
   - SSNs (standard and loose/bare 9-digit)
   - Phone numbers
   - Physical addresses (high-profile whitelist allowed)
   - Names (optional, uncommon only, respects safe/whitelisted names)
2. Preserves:
   - First-person pronouns
   - Common English pronouns
   - Safe/whitelisted names

Usage:
------
    safe_text = redact_pii(
        text=raw_text,
        redact_names=True,    # set False for testing/debugging
        use_fuzzy=True,
        threshold=85
    )
"""

import re
import json
from pathlib import Path
from rapidfuzz import fuzz

# Attempt to import spaCy for NER-based name detection
try:
    import spacy
    NLP = spacy.load("en_core_web_sm")
    SPACY_AVAILABLE = True
except ImportError:
    NLP = None
    SPACY_AVAILABLE = False

# --------------------
# Paths & Data Loader
# --------------------
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# High-profile addresses whitelist
HIGH_PROFILE_ADDRESSES_PATH = DATA_DIR / "high-profile-addresses.json"
HIGH_PROFILE_ADDRESSES = set()
if HIGH_PROFILE_ADDRESSES_PATH.exists():
    with HIGH_PROFILE_ADDRESSES_PATH.open("r", encoding="utf-8") as f:
        HIGH_PROFILE_ADDRESSES.update(json.load(f))

# Dynamic international names loader
COMMON_NAMES = set()
for name_file in DATA_DIR.glob("names_*.json"):
    with name_file.open("r", encoding="utf-8") as f:
        names = json.load(f)
        COMMON_NAMES.update(name.lower() for name in names)

# Add extra celebrity / safe names manually
SAFE_NAMES = {"zendaya", "beyonce", "gandhi"}
COMMON_NAMES.update(SAFE_NAMES)

# --------------------
# Safe Pronouns / Contractions
# --------------------
SAFE_PRONOUNS = {
    "i", "i'm", "me", "you", "she", "her", "he", "him",
    "his", "they", "them", "theirs", "we", "us", "our", "ours"
}

# --------------------
# Regex Patterns
# --------------------
EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
SSN_PATTERN = r"\b\d{3}-\d{2}-\d{4}\b"
SSN_LOOSE_PATTERN = r"^\d{9}$"
PHONE_PATTERN = r"\b(?:\+?1[-.\s]?|)(?:\(?\d{3}\)?[-.\s]?|\d{3}[-.\s]?)\d{3}[-.\s]?\d{4}\b"
ADDRESS_PATTERN = r"\d{1,5}\s\w+(?:\s\w+){0,4}\s(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Way)\b"

# --------------------
# Core Redaction Function
# --------------------
def redact_pii(text: str, redact_names: bool = False, use_fuzzy: bool = True, threshold: int = 85) -> str:
    """
    Redacts PII from input text.

    Parameters:
    -----------
    text : str
        Raw text to be redacted.
    redact_names : bool
        If True, redacts uncommon names (requires spaCy).
        Default is False for testing/debugging.
    use_fuzzy : bool
        Whether to apply fuzzy matching for high-profile addresses.
    threshold : int
        Threshold for fuzzy matching of high-profile addresses.

    Returns:
    --------
    str
        Text with PII redacted (emails, phones, SSNs, addresses, optional names).
    """

    safe_text = text

    # -----------------------
    # Loose SSN detection
    # -----------------------
    digits_only = re.sub(r"[^\d]", "", safe_text)
    if len(digits_only) == 9 and re.match(SSN_LOOSE_PATTERN, digits_only):
        safe_text = re.sub(re.escape(digits_only), "[SSN]", safe_text)

    # -----------------------
    # Exact regex replacements
    # -----------------------
    safe_text = re.sub(EMAIL_PATTERN, "[EMAIL]", safe_text)
    safe_text = re.sub(SSN_PATTERN, "[SSN]", safe_text)
    safe_text = re.sub(PHONE_PATTERN, "[PHONE]", safe_text)

    # -----------------------
    # High-profile address redaction (fuzzy optional)
    # -----------------------
    matches = re.findall(ADDRESS_PATTERN, safe_text)
    for match in matches:
        keep = any(
            (use_fuzzy and fuzz.ratio(match.lower(), hp.lower()) >= threshold)
            or (not use_fuzzy and match.lower() == hp.lower())
            for hp in HIGH_PROFILE_ADDRESSES
        )
        if not keep:
            safe_text = safe_text.replace(match, "[ADDRESS]")

    # -----------------------
    # Name redaction: only if requested and spaCy available
    # -----------------------
    if redact_names and SPACY_AVAILABLE:
        doc = NLP(safe_text)
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                # Redact if not in COMMON_NAMES
                if ent.text.lower() not in COMMON_NAMES:
                    safe_text = safe_text.replace(ent.text, "[NAME]")

    return safe_text
