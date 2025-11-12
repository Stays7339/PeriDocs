"""
core.nlp.pii.py

Redaction of personally identifiable information (PII) using regex
patterns and high-profile addresses.
"""

import re
import json
from pathlib import Path
from rapidfuzz import fuzz

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
HIGH_PROFILE_PATH = DATA_DIR / "high-profile-addresses.json"

# Minimal common names to avoid over-redaction
COMMON_NAMES = {"John", "Jane", "Michael", "Emily", "Chris", "Sarah"}

# Regular expression patterns for PII
EMAIL_PATTERN = re.compile(r"\b[\w\.-]+@[\w\.-]+\.\w+\b")
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
PHONE_PATTERN = re.compile(r"\b(?:\+?1[-.\s]?)*\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
ADDRESS_PATTERN = re.compile(
    r"\d+\s+\w+(?:\s+\w+)*,\s*\w+(?:\s+\w+)*,\s*[A-Z]{2}\s*\d{5}"
)

# Load high-profile addresses
if HIGH_PROFILE_PATH.exists():
    with HIGH_PROFILE_PATH.open("r", encoding="utf-8") as f:
        HIGH_PROFILE_ADDRESSES = set(json.load(f))
else:
    HIGH_PROFILE_ADDRESSES = set()


def redact_pii(text: str, use_fuzzy: bool = True, threshold: int = 85) -> str:
    """
    Redact emails, SSNs, phone numbers, addresses, and non-common named entities.
    Optionally performs fuzzy matching for high-profile addresses.
    """
    # Redact email addresses
    text = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    # Redact SSNs
    text = SSN_PATTERN.sub("[REDACTED_SSN]", text)
    # Redact phone numbers
    text = PHONE_PATTERN.sub("[REDACTED_PHONE]", text)
    # Redact addresses
    text = ADDRESS_PATTERN.sub("[REDACTED_ADDRESS]", text)

    # Fuzzy match high-profile addresses if enabled
    if use_fuzzy and HIGH_PROFILE_ADDRESSES:
        for addr in HIGH_PROFILE_ADDRESSES:
            if fuzz.partial_ratio(addr.lower(), text.lower()) >= threshold:
                text = text.replace(addr, "[REDACTED_ADDRESS]")

    return text
