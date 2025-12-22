# ==========================================
# core/nlp/crisis_detector.py
# Save-state updated 202512221126 (YYYYMMDDhhmm)
# ==========================================
from typing import List
from .orthography import token_lemmas
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
    "cant go on",
    "tired of living",
    "wish i were dead",
    "end it all",
    "ultimate price",
    "unalive",
    "sewerslide",
]

# ========================
# Debug toggle
# ========================
DEBUG = True

# ========================
# Normalization helpers
# ========================
_PUNCT_RE = re.compile(r"[^a-z0-9]+")

def normalize_text(text: str) -> str:
    """
    Lowercase, strip punctuation, collapse to spaces.
    Deterministic and reversible for audit.
    """
    return _PUNCT_RE.sub(" ", text.lower()).strip()

def compress_text(text: str) -> str:
    """
    Boundary-free representation for adversarial spacing.
    """
    return normalize_text(text).replace(" ", "")

# ========================
# Token similarity
# ========================
def token_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

# ========================
# Anchor vocabularies
# ========================
SELF_HARM_ANCHORS = {
    "die", "dead", "kill", "suicide", "unalive"
}

SELF_REFERENT_ANCHORS = {
    "i", "me", "my", "myself", "life"
}

COGNITIVE_INTENT_VERBS = {
    "think", "thinking", "thought",
    "consider", "considering",
    "planning", "plan",
    "feel", "feels", "felt"
}

TEMPORAL_COMMITMENTS = {
    "now", "today", "tomorrow", "tonight",
    "soon", "later", "anymore", "never"
}

THIRD_PERSON_ANCHORS = {
    "he", "she", "they", "him", "her", "them"
}

# ========================
# Anchor-pair check
# ========================
def anchor_pair_present(tokens: List[str]) -> bool:
    return (
        any(t in SELF_HARM_ANCHORS for t in tokens)
        and any(t in SELF_REFERENT_ANCHORS for t in tokens)
    )

# ========================
# Implicit self-reference inference
# ========================
def implicit_self_from_infinitive(tokens: List[str]) -> bool:
    """
    Infers first-person self-reference when a cognitive intent verb
    governs an infinitive ("planning to X") and no explicit
    third-person subject is present.

    Deterministic linguistic rule.
    """
    for i, tok in enumerate(tokens):
        if tok in COGNITIVE_INTENT_VERBS:
            # look ahead for "to <verb>"
            for j in range(i + 1, min(i + 4, len(tokens) - 1)):
                if tokens[j] == "to":
                    # block if third-person subject appears anywhere in window
                    if any(t in THIRD_PERSON_ANCHORS for t in tokens):
                        return False
                    return True
    return False

# ========================
# Async crisis check
# ========================
async def check_crisis_phrases_async(
    text: str,
    match_threshold: float = 0.8,
    token_similarity_threshold: float = 0.85
) -> List[str]:

    if not text:
        return []

    # -------- representations --------
    normalized = normalize_text(text)
    compressed = compress_text(text)

    tokens = token_lemmas(normalized)
    tokens = [t for t in tokens if t]

    hits: List[str] = []

    # ======================================================
    # CHANNEL 1: token sliding-window phrase detection
    # ======================================================
    for phrase in _CRISIS_PHRASES:
        phrase_norm = normalize_text(phrase)
        phrase_tokens = phrase_norm.split()
        n = len(phrase_tokens)

        for start in range(len(tokens)):
            matched = 0
            j = 0
            i = start

            while i < len(tokens) and j < n:
                if token_similarity(tokens[i], phrase_tokens[j]) >= token_similarity_threshold:
                    matched += 1
                    j += 1
                else:
                    # allow one filler token for short phrases
                    if n <= 3:
                        i += 1
                        continue
                    break
                i += 1

            if matched == n:
                window = tokens[start:i]
                if n <= 3 and not anchor_pair_present(window):
                    continue
                hits.append(phrase)
                if DEBUG:
                    print(f"[CRISIS DEBUG] Token match '{phrase}' via {window}")
                break

    # ======================================================
    # CHANNEL 2: compressed-text substring detection
    # ======================================================
    for phrase in _CRISIS_PHRASES:
        phrase_comp = compress_text(phrase)
        if phrase_comp and phrase_comp in compressed:
            hits.append(phrase)
            if DEBUG:
                print(
                    f"[CRISIS DEBUG] Compressed match '{phrase}' "
                    f"in '{compressed}'"
                )

    # ======================================================
    # CHANNEL 3: implicit anchor co-occurrence
    # ======================================================
    for i, tok in enumerate(tokens):
        if tok in SELF_HARM_ANCHORS:
            window = tokens[max(0, i - 6): min(len(tokens), i + 7)]

            self_ref_present = (
                any(t in SELF_REFERENT_ANCHORS for t in window)
                or implicit_self_from_infinitive(window)
            )

            if (
                self_ref_present
                and (
                    any(t in TEMPORAL_COMMITMENTS for t in window)
                    or any(t in COGNITIVE_INTENT_VERBS for t in window)
                )
            ):
                hits.append(f"implicit:{tok}")
                if DEBUG:
                    print(
                        f"[CRISIS DEBUG] Implicit anchor '{tok}' "
                        f"with context {window}"
                    )

    return list(dict.fromkeys(hits))  # deterministic de-dupe

# ========================
# Async crisis notification
# ========================
async def crisis_notification_async(
    text: str,
    match_threshold: float = 0.8,
    token_similarity_threshold: float = 0.85
) -> str:
    matches = await check_crisis_phrases_async(
        text,
        match_threshold,
        token_similarity_threshold
    )
    if not matches:
        return ""
    return (
        "⚠️ Your writing suggests the possibility of emotional or mental health strain. "
        "There are professionals and services outside of PeriDocs equipped to provide guidance."
    )

# ========================
# Public accessor
# ========================
def get_crisis_phrases() -> List[str]:
    return list(_CRISIS_PHRASES)
