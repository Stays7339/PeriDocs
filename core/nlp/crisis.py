"""
core.nlp.crisis.py

Functions to detect crisis-related content in user text.
"""

from typing import List
import re

# Crisis phrases list (from legacy app/nlp.py)
CRISIS_PHRASES = [
    "suicide",
    "self harm",
    "self-harm",
    "cutting",
    "overdose",
    "kill myself",
    "ending it",
    "hopeless",
    "worthless",
    "no way out",
    "die alone",
    "want to die",
    "can't go on",
    "overwhelmed",
]

def check_crisis_phrases(text: str) -> List[str]:
    """
    Returns a list of crisis phrases found in the input text.
    Case-insensitive search.
    """
    if not text:
        return []
    text_lower = text.lower()
    found_phrases = [phrase for phrase in CRISIS_PHRASES if phrase in text_lower]
    return found_phrases

def crisis_notification(text: str) -> str:
    """
    If any crisis phrase is found in the text, returns a
    standardized warning message. Otherwise, returns empty string.
    """
    matches = check_crisis_phrases(text)
    if not matches:
        return ""
    return (
        "⚠️ Warning: Your entry contains language that may indicate a mental health crisis. "
        "Please reach out to trained professionals or emergency services if needed."
    )
