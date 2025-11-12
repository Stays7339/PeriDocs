"""
app/helpers/display_last_entry.py

Provides functions to fetch and display the most recent journal entry,
including sentiment, repetition, and emotion summaries.
"""

from typing import Optional, Dict, Any
from app.helpers.file_ops import load_data
from app.helpers.json_safe import json_safe
from core.nlp.sentiment_analysis import sentiment_label

def display_last_entry(journals_path: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves the most recent journal entry and returns a summary
    containing key fields for display.

    Returns:
        dict with keys:
            - 'id': SHA8 entry ID
            - 'timestamp': entry timestamp
            - 'excerpt': first ~15 words of the entry
            - 'sentiment': textual sentiment label
            - 'repetition': repetition score or %
            - 'emotions': dict of emotion intensities
    """
    entries = load_data(journals_path)
    if not entries:
        return None

    last_entry = entries[-1]
    nlp_data = last_entry.get('nlp', {})

    text_excerpt = last_entry.get('text', '').split()
    excerpt = ' '.join(text_excerpt[:15]) + ('...' if len(text_excerpt) > 15 else '')

    sentiment_score = nlp_data.get('sentiment', 0)
    repetition_score_val = nlp_data.get('repetition', 0)
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
