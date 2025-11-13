"""
core/nlp/crisis.py

Functions to detect crisis-related content in user text.
"""

from typing import List
from core.nlp.anchors import get_crisis_phrases

# Behavioral functions remain in crisis.py
def check_crisis_phrases(text: str) -> List[str]:
    """
    Returns a list of crisis phrases found in the input text.
    Case-insensitive search.
    """
    if not text:
        return []
    text_lower = text.lower()
    crisis_phrases = get_crisis_phrases()
    found_phrases = [phrase for phrase in crisis_phrases if phrase in text_lower]
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
