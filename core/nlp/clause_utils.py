# ==========================================
# core/nlp/clause_utils.py
# save-state: 202512172107
# ==========================================

import re
from typing import List

CLAUSE_RE = r"[^.!?]+[.!?]?"  # basic clause/sentence split; can be refined

def split_into_clauses(text: str) -> List[str]:
    """
    Splits text into clauses (sentence-level granularity), due to token limits for all-roberta-large-v1
    """
    import re
    return [cl.strip() for cl in re.findall(CLAUSE_RE, text) if cl.strip()]

def sliding_window_clauses(clauses: List[str], max_words: int = 100) -> List[str]:
    """
    Optionally merge clauses into windows of ~max_words to avoid too short embeddings.
    """
    windows = []
    current = []
    current_len = 0
    for cl in clauses:
        n_words = len(cl.split())
        if current_len + n_words > max_words and current:
            windows.append(" ".join(current))
            current = []
            current_len = 0
        current.append(cl)
        current_len += n_words
    if current:
        windows.append(" ".join(current))
    return windows
