# ==========================================
# core/nlp/orthography.py
# updated 20251217131355
# ==========================================

import re
from typing import List, Dict, Any

TOKEN_RE = re.compile(r"\b\w+(?:['’]\w+)?\b", flags=re.UNICODE)

def clean_text(text: str) -> str:
    """
    Normalize input text by trimming leading/trailing whitespace
    and collapsing all internal whitespace to single spaces.
    
    This is safe for storage, indexing, and user interface display.

    Parameters:
    -----------
    text : str
        Raw input string.

    Returns:
    --------
    str
        Whitespace-normalized string.
    """
    return re.sub(r"\s+", " ", text.strip())


def tokenize_text(text: str) -> List[Dict[str, Any]]:
    """
    Tokenize input text into word-level units using a simple regex.

    Essential for token-level pipelines (e.g., PII detection, lexicon checks)

    Each token is returned as a dictionary containing:
        - 'text': the original token
        - 'lemma': lowercase form (placeholder for future lemmatization)
        - 'pos': part-of-speech placeholder (currently 'X')

    Parameters:
    -----------
    text : str
        Normalized string to tokenize.

    Returns:
    --------
    List[Dict[str, Any]]
        List of token dictionaries, suitable for downstream NLP pipelines.
    """
    tokens = TOKEN_RE.findall(text)
    return [{"text": t, "lemma": t.lower(), "pos": "X"} for t in tokens]


def token_lemmas(text: str) -> List[str]:
    """
    Return a list of lowercase lemma forms of tokens for fast lookup.
    
    Useful for lemma-aware crisis detection:
        e.g., "kill", "killed", "killing" → all map to "kill"
    """
    return [t["lemma"] for t in tokenize_text(text)]
