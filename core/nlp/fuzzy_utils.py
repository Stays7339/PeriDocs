# core/nlp/fuzzy_utils.py
"""
Fuzzy matching lexicon utilities and dynamic lexicon loader for PeriDocs.
- Uses rapidfuzz if available (fast); falls back to simple ratio when not.
- Loads dynamic lexicons from data/dynamic_lexicons.json (created if missing).
"""

import json
import os
from typing import Set, Dict, Tuple, Optional, List

try:
    from rapidfuzz import process, fuzz
    _HAS_RAPIDFUZZ = True
except Exception:
    _HAS_RAPIDFUZZ = False

PACKAGE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(PACKAGE_ROOT, "data")
DYNAMIC_LEXICONS_PATH = os.path.join(DATA_DIR, "dynamic_lexicons.json")
SUGGESTIONS_PATH = os.path.join(DATA_DIR, "lexicon_suggestions.json")

DEFAULT_THRESHOLD = 85  # tune from 75..95

def _ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)

def load_dynamic_lexicons() -> Dict[str, Set[str]]:
    """
    Returns dynamic lexicons stored in data/dynamic_lexicons.json
    Format: { "joy": ["hopeful","..."], "fear": ["..."], ... }
    """
    _ensure_data_dir()
    if not os.path.exists(DYNAMIC_LEXICONS_PATH):
        with open(DYNAMIC_LEXICONS_PATH, "w", encoding="utf-8") as fh:
            json.dump({}, fh)
        return {}
    with open(DYNAMIC_LEXICONS_PATH, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    # normalize to sets and lowercase
    return {k: set(w.lower() for w in v) for k, v in data.items()}

def save_dynamic_lexicons(d: Dict[str, Set[str]]):
    _ensure_data_dir()
    serial = {k: sorted(list(v)) for k, v in d.items()}
    with open(DYNAMIC_LEXICONS_PATH, "w", encoding="utf-8") as fh:
        json.dump(serial, fh, indent=2, ensure_ascii=False)

def save_suggestions(suggestions: List[Dict]):
    _ensure_data_dir()
    with open(SUGGESTIONS_PATH, "w", encoding="utf-8") as fh:
        json.dump(suggestions, fh, indent=2, ensure_ascii=False)

def fuzzy_best_match(token: str, choices: Set[str], limit: int = 1) -> Optional[Tuple[str, int]]:
    """
    Return (best_choice, score) or None. Token and choices expected lowercase.
    Uses rapidfuzz if available; otherwise uses naive ratio.
    """
    if not choices:
        return None
    token = token.lower()
    if _HAS_RAPIDFUZZ:
        result = process.extractOne(token, list(choices), scorer=fuzz.ratio)
        if result:
            choice, score, _ = result
            return choice, int(score)
        return None
    # fallback: simple distance using Python built-ins (slow for large sets)
    # We'll compute a very cheap Levenshtein-like ratio (not production-grade).
    best = None
    best_score = -1
    for c in choices:
        # quick length check
        if abs(len(token) - len(c)) > max(3, int(0.4 * len(c))):
            continue
        # character overlap heuristic
        overlap = sum(1 for ch in token if ch in c) 
        score = int(100 * overlap / max(1, len(c)))
        if score > best_score:
            best_score = score
            best = c
    if best is None:
        return None
    return best, best_score

def fuzzy_matches_above(token: str, choices: Set[str], threshold: int = DEFAULT_THRESHOLD) -> List[Tuple[str, int]]:
    """Return list of (choice, score) with score >= threshold, sorted by score desc."""
    token = token.lower()
    results = []
    if _HAS_RAPIDFUZZ:
        hits = process.extract(token, list(choices), scorer=fuzz.ratio, limit=20)
        for choice, score, _ in hits:
            if int(score) >= threshold:
                results.append((choice, int(score)))
    else:
        for c in choices:
            m = fuzzy_best_match(token, {c})
            if m and m[1] >= threshold:
                results.append((c, m[1]))
    results.sort(key=lambda x: x[1], reverse=True)
    return results

def get_combined_lexicons(static_lexicons: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    """
    Merge static anchors (from anchors.py) with dynamic lexicons stored in data/dynamic_lexicons.json.
    Returns a new dict where all words are lowercase sets.
    """
    dyn = load_dynamic_lexicons()
    combined = {}
    for k, v in static_lexicons.items():
        combined[k] = set(w.lower() for w in v)
        if k in dyn:
            combined[k].update(dyn[k])
    # include keys that exist only in dynamic
    for k, v in dyn.items():
        if k not in combined:
            combined[k] = set(v)
    return combined
