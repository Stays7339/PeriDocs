"""
app/helpers/top_matches.py

API-ready top matches + JSON-safe outputs based on vector similarity,
repetition, and sentiment adjustments.
"""

from typing import List, Dict, Any
from app.helpers.similarity import compute_similarity
from app.helpers.json_safe import json_safe

def find_top_matches(
    entry_vec: List[float],
    all_entries: List[Dict[str, Any]],
    top_n: int = 20,
    sentiment_weight: float = 0.1,
    repetition_weight: float = 0.1
) -> List[Dict[str, Any]]:
    """
    Returns top N most similar entries to entry_vec from all_entries.
    
    Each entry is a dictionary expected to contain:
        - 'embedding' (List[float])
        - 'nlp' (dict with 'sentiment', 'repetition')
        - 'text' (original text)
    
    Adjusts similarity based on sentiment and repetition if provided.
    Returns JSON-safe output.
    """
    scored_entries = []
    
    for e in all_entries:
        vec = e.get('embedding')
        base_score = compute_similarity(entry_vec, vec)
        
        sentiment = e.get('nlp', {}).get('sentiment', 0.0)
        repetition = e.get('nlp', {}).get('repetition', 0.0)
        
        adjusted_score = base_score
        adjusted_score += sentiment_weight * sentiment
        adjusted_score += repetition_weight * repetition
        
        scored_entries.append({
            'entry': e,
            'score': adjusted_score
        })
    
    # Sort descending by score
    scored_entries.sort(key=lambda x: x['score'], reverse=True)
    
    top_entries = [json_safe(e['entry']) for e in scored_entries[:top_n]]
    
    return top_entries
