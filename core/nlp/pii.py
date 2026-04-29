# ==========================================
# core/nlp/pii.py
# Save-state 2026-03-05T19:57:20-04:00
# ==========================================


import re
import json
import asyncio
from pathlib import Path
from rapidfuzz import fuzz

# --------------------
# Force spaCy availability
# --------------------
try:
    import spacy
    NLP = spacy.load("en_core_web_sm")
except ImportError as e:
    raise RuntimeError(
        "spaCy is required for name redaction. Please install spaCy and the 'en_core_web_sm' model."
    ) from e

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


# Add extra celebrity / safe names manually
SAFE_NAMES = {"zendaya", "beyonce", "gandhi"}

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
def redact_pii(text: str, redact_names: bool = True, use_fuzzy: bool = True, threshold: int = 85) -> str:
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
    if redact_names:
            doc = NLP(safe_text)
            for ent in doc.ents:
                if ent.label_ == "PERSON":
                    if not is_safe_name(ent.text):
                        safe_text = safe_text.replace(ent.text, "[NAME]")

    return safe_text


def is_safe_name(name: str) -> bool:
    """
    Check whether a PERSON entity is in the safe whitelist.
    """
    return any(fuzz.ratio(name.lower(), safe.lower()) >= 90 for safe in SAFE_NAMES)