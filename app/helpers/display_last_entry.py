"""
app/helpers/display_last_entry.py

Provides functions to fetch and display the most recent journal entry,
including sentiment, repetition, and emotion summaries.
"""

from typing import Optional, Dict, Any
from app.helpers.file_ops import load_data
from app.helpers.json_safe import json_safe
from core.nlp import repetition_score

# ----------------------
# Local sentiment_label helper (merged here)
# ----------------------
def sentiment_label(score: float) -> str:
    if score > 0.05:
        return "positive"
    elif score < -0.05:
        return "negative"
    return "neutral"

def display_last_entry(journals_path: str) -> Optional[Dict[str, Any]]:
    entries = load_data(journals_path)
    if not entries:
        return None

    # Handle nested lists or malformed entries
    last_entry = next((e for e in reversed(entries) if isinstance(e, dict)), None)
    if last_entry is None:
        return None

    nlp_data = last_entry.get('nlp', {})

    text_excerpt = last_entry.get('safe_text', '').split()
    excerpt = ' '.join(text_excerpt[:15]) + ('...' if len(text_excerpt) > 15 else '')

    sentiment_score = nlp_data.get('sentiment', 0)
    repetition_score_val = repetition_score(last_entry.get('safe_text', ''))
    emotions = nlp_data.get('emotions', {})

    summary = {
        'id': last_entry.get('id'),
        'timestamp': last_entry.get('timestamp'),
        'excerpt': excerpt,
        'sentiment': sentiment_label(sentiment_score),
        'repetition': repetition_score_val,
        'emotions': json_safe(emotions)
    }

    return summary
