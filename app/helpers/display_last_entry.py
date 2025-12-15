# ==========================================
# app/helpers/display_last_entry.py
# save-state updated 202512151615
# ==========================================
"""
Provides functions to fetch and display the most recent journal entry,
including sentiment, repetition, emotion summaries, and normalized embeddings.
"""

from typing import Optional, Dict, Any
from app.helpers.file_ops import load_data
from app.helpers.json_safe import json_safe
from app.helpers.vector_ops import normalize_vector  # centralized normalization helper


def display_last_entry(journals_path: str) -> Optional[Dict[str, Any]]:
    """
    Fetches the most recent journal entry and returns a summary
    including:
      - truncated text excerpt
      - normalized embedding
      - placeholder emotion info
      - repetition multiplier
    """
    entries = load_data(journals_path)
    if not entries:
        return None

    # Grab the last valid dictionary entry
    last_entry = next((e for e in reversed(entries) if isinstance(e, dict)), None)
    if last_entry is None:
        return None

    # Prepare a short text excerpt (first 15 words)
    text_excerpt = last_entry.get('safe_text', '').split()
    excerpt = ' '.join(text_excerpt[:15]) + ('...' if len(text_excerpt) > 15 else '')

    # Normalize the embedding if it exists
    embedding = last_entry.get('nlp', {}).get('embedding')
    normalized_embedding = normalize_vector(embedding)

    summary = {
        'id': last_entry.get('sha8'),
        'timestamp': last_entry.get('timestamp'),
        'excerpt': excerpt,
        'embedding': normalized_embedding,
        'emotions': {},           # placeholder; will fill with clustering later
        'dominant_emotion': None, # placeholder
        'repetition': last_entry.get('repetition_multiplier', 0.0),
    }

    return summary
