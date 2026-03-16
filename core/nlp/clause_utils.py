# ==========================================
# core/nlp/clause_utils.py
# save-state: 2026-03-15T17:38:50-05:00
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

def sliding_window_clauses(clauses: List[str], max_words: int) -> List[str]:
    """
    Merge clauses into windows of <= max_words.
    Spins off any single clause  / sentence that exceeds max_words, and puts it into a new window.
    Guarantees no window exceeds max_words.
    Deterministic and replay-safe.

    NOTE: this uses word count as a proxy for token count. 
    That is still technically approximate, but its safe at 90 words per auto-window.
    This count is set within process_entry.py for the sake of uniform operations.
    With RoBERTa truncating at 128 word pieces, 90 words is conservative enough that entries 
    will not realistically hit truncation unless the text is extremely fragment-heavy.
    If the software developers ever want absolute certainty, they’d need to count tokenizer tokens before embedding.
    But that introduces model dependency and weakens replay determinism unless tokenizer version is frozen.
    We're choosing to not over-complicate things by keeping it here.
    """
    windows: List[str] = []
    current: List[str] = []
    current_len = 0

    for cl in clauses:
        words = cl.split()
        n_words = len(words)

        # ---- HARD SPLIT LONG CLAUSES ----
        if n_words > max_words:
            # flush current window first
            if current:
                windows.append(" ".join(current))
                current = []
                current_len = 0

            # chunk the long clause deterministically
            for i in range(0, n_words, max_words):
                chunk = words[i:i + max_words]
                windows.append(" ".join(chunk))
            continue

        # ---- NORMAL WINDOW MERGE ----
        if current_len + n_words > max_words:
            windows.append(" ".join(current))
            current = []
            current_len = 0

        current.append(cl)
        current_len += n_words

    if current:
        windows.append(" ".join(current))

    return windows