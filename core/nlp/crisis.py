"""
core/nlp/crisis.py
save-state updated 202511231610 (date and time formatted as follows: YYYYMMDDhhmm)

Functions to detect crisis-related content in user text.
"""

from typing import List
from core.nlp.anchors import get_crisis_phrases

def check_crisis_phrases(text: str) -> List[str]:
    """Return crisis phrases found in text, case-insensitive."""
    if not text:
        return []
    text_lower = text.lower()
    crisis_phrases = get_crisis_phrases()
    return [phrase for phrase in crisis_phrases if phrase in text_lower]

def crisis_notification(text: str) -> str:
    """Return standardized warning message if crisis phrases are detected."""
    matches = check_crisis_phrases(text)
    if not matches:
        return ""
    return (
        "⚠️ Your writing suggests the possibility of emotional or mental health strain. There are professionals and services outside of PeriDocs equipped to provide guidance."
    )
