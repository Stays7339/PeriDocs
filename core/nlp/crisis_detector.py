# ==========================================
# core/nlp/crisis_detector.py
# Save-state updated 202512202016
# ==========================================
from typing import List
from .orthography import token_lemmas
import asyncio
import re
from difflib import SequenceMatcher

# ========================
# Crisis phrase blacklist
# ========================
_CRISIS_PHRASES = [
    "kill myself",
    "want to die",
    "end my life",
    "suicide",
    "can't go on",
    "tired of living",
    "wish i were dead",
    "end it all",
    "ultimate price",
    "unalive",
    "sewerslide"
]

# ========================
# Debug toggle
# ========================
DEBUG = True

# ========================
# Helper: token similarity
# ========================
def token_similarity(token1: str, token2: str) -> float:
    """
    Returns a similarity score between 0 and 1 for two tokens.
    Uses SequenceMatcher ratio for character-level fuzzy matching.
    """
    return SequenceMatcher(None, token1, token2).ratio()

# ========================
# Phase 3: implicit intent vocab
# ========================
SELF_HARM_ANCHORS = {
    "die", "dead", "kill", "suicide", "unalive"
}

SELF_REFERENT_ANCHORS = {
    "myself", "me", "i", "life"
}

COGNITIVE_INTENT_VERBS = {
    "think", "thinking", "thought",
    "consider", "considering",
    "about",
    "planning", "plan"
}

TEMPORAL_COMMITMENTS = {
    "today", "tomorrow", "tonight",
    "soon", "later", "next"
}

# ========================
# Helper: required tokens
# ========================
def required_tokens_to_match(n_phrase: int, match_threshold: float) -> int:
    """
    Determines how many tokens must match for a phrase to trigger.
    Short phrases (≤3 tokens) keep 1-word flexibility, but semantic anchor check applies.
    """
    if n_phrase <= 3:
        return 1
    return max(1, int(n_phrase * match_threshold))

# ========================
# Helper: check anchor-pair for short phrases
# ========================
def short_phrase_anchor_pair_check(phrase_tokens: List[str], ngram: List[str]) -> bool:
    """
    Returns True if for short phrases (≤3 tokens), the ngram contains at least
    one verb-like harm anchor AND one self-referent/terminal outcome anchor.
    """
    harm_present = any(tok in SELF_HARM_ANCHORS for tok in ngram)
    selfref_present = any(tok in SELF_REFERENT_ANCHORS for tok in ngram)
    return harm_present and selfref_present

# ========================
# Async crisis check
# ========================
async def check_crisis_phrases_async(
    text: str,
    match_threshold: float = 0.8,
    token_similarity_threshold: float = 0.8
) -> List[str]:
    """
    Async function that checks text for crisis phrases using
    order-aware but gap-tolerant fuzzy token matching.

    Returns list of matched phrases.
    """
    if not text:
        return []

    # Tokenize and normalize
    tokens = token_lemmas(text)
    tokens_lower = [tok.lower() for tok in tokens if tok.strip()]
    hits: List[str] = []

    # ======================================================
    # Phase 1 + 2: explicit phrase matching (existing logic)
    # ======================================================
    for phrase in _CRISIS_PHRASES:
        phrase_tokens = [w.lower() for w in re.split(r"\s+", phrase) if w.strip()]
        n_phrase = len(phrase_tokens)
        if n_phrase == 0:
            continue

        min_required = required_tokens_to_match(n_phrase, match_threshold)

        # Adjust similarity threshold for short phrases
        effective_similarity = token_similarity_threshold
        if n_phrase <= 3:
            effective_similarity = 0.9  # stricter for short phrases

        # ----------------------------
        # Phase 1: Exact n-gram window
        # ----------------------------
        for i in range(len(tokens_lower) - n_phrase + 1):
            ngram = tokens_lower[i:i + n_phrase]
            matched_count = sum(
                1
                for pt, nt in zip(phrase_tokens, ngram)
                if token_similarity(pt, nt) >= effective_similarity
            )
            # For short phrases, also enforce anchor-pair semantic check
            if matched_count >= min_required:
                if n_phrase <= 3:
                    if not short_phrase_anchor_pair_check(phrase_tokens, ngram):
                        continue  # skip this ngram, anchor-pair not satisfied
                hits.append(phrase)
                if DEBUG:
                    print(
                        f"[CRISIS DEBUG] Exact n-gram matched '{phrase}' "
                        f"at tokens {i}-{i+n_phrase}: {ngram} "
                        f"(threshold={effective_similarity})"
                    )
                break
        else:
            # ------------------------------------
            # Phase 2: Order-aware gap-tolerant scan
            # ------------------------------------
            matched = 0
            j = 0  # phrase index

            for tok in tokens_lower:
                if j < n_phrase and token_similarity(phrase_tokens[j], tok) >= effective_similarity:
                    matched += 1
                    j += 1
                if matched >= min_required:
                    # short phrase anchor-pair enforcement
                    if n_phrase <= 3:
                        window_ngram = tokens_lower[max(0, i-1):i+n_phrase+1]  # rough window
                        if not short_phrase_anchor_pair_check(phrase_tokens, window_ngram):
                            break
                    hits.append(phrase)
                    if DEBUG:
                        print(
                            f"[CRISIS DEBUG] Fuzzy matched '{phrase}' "
                            f"(matched {matched}/{n_phrase}, threshold={effective_similarity})"
                        )
                    break

    # ======================================================
    # Phase 3: implicit self-harm anchor detection (balanced)
    # ======================================================
    for i, tok in enumerate(tokens_lower):
        if tok in SELF_HARM_ANCHORS:
            window_start = max(0, i - 4)
            window_end = min(len(tokens_lower), i + 5)
            context = tokens_lower[window_start:window_end]

            # Check for meaningful context: temporal or cognitive-intent
            temporal_present = any(w in TEMPORAL_COMMITMENTS for w in context)
            cognitive_present = any(w in COGNITIVE_INTENT_VERBS for w in context)

            if temporal_present or cognitive_present:
                hits.append(f"implicit:{tok}")
                if DEBUG:
                    print(
                        f"[CRISIS DEBUG] Implicit self-harm anchor detected near '{tok}' "
                        f"with context {context} "
                        f"(temporal={temporal_present}, cognitive={cognitive_present})"
                    )

    # Dispose parsing artifacts
    del tokens
    del tokens_lower

    return hits

# ========================
# Async crisis notification
# ========================
async def crisis_notification_async(
    text: str,
    match_threshold: float = 0.8,
    token_similarity_threshold: float = 0.8
) -> str:
    """
    Returns standardized warning message if crisis phrases are detected.
    """
    matches = await check_crisis_phrases_async(
        text,
        match_threshold=match_threshold,
        token_similarity_threshold=token_similarity_threshold
    )
    if not matches:
        return ""
    return (
        "⚠️ Your writing suggests the possibility of emotional or mental health strain. "
        "There are professionals and services outside of PeriDocs equipped to provide guidance."
    )

# ========================
# Public accessor (tests)
# ========================
def get_crisis_phrases() -> List[str]:
    """
    Returns the active crisis phrase list.
    Intended for test harnesses only.
    """
    return list(_CRISIS_PHRASES)
