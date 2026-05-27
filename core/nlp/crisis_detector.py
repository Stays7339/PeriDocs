# ==========================================
# core/nlp/crisis_detector.py
# Save-state updated 2026-05-27T14:01:15-04:00 (YYYYMMDDhhmm)
# ==========================================

"""
Crisis Detector Module

Detects high-risk self-harm language in user text. Designed to catch
self-harm signals while minimizing false positives. Human moderators
can review flagged content, and users are never acted upon blindly.

Crisis Phrase Blacklist:
------------------------
Explicit phrases indicating a high likelihood of self-harm. Detection
is deterministic and word-based / phrase-based (i.e. tokens), plus compressed-text channels
handle misspellings or punctuation tricks. List is intentionally small
for easy audit by non-technical reviewers.

Debug Mode:
-----------
When True, prints detailed information about matches, including which
tokens triggered a flag. Useful for developers and moderator training.

Text Normalization:
-------------------
Lowercase conversion, punctuation removal, and space collapsing.
Compressed text removes spaces entirely to prevent adversarial
spacing attempts (e.g., "k i l l").

Token Similarity:
-----------------
SequenceMatcher computes a similarity score (0–1) between words and phrases (i.e. tokens).
Detects minor typos (e.g., "dyingg" → "dying") without excessive false positives.

Morphological Base Forms:
-------------------------
Verb forms (present, past, progressive, etc.) are mapped to their
base forms dictated within this code file if explicitly specified (e.g., "killed" → "kill").
Reduces false positives and simplifies downstream logic.

Anchor Checks:
--------------
- Anchor-pair: requires both a self-harm term and a self-reference.
- Implicit self-reference: detects first-person context in constructions
  like "planning to X" even when "I" is omitted, while avoiding third-person references.

Detection Channels:
-------------------
1. Direct phrase detection: word/phrase/token sliding-window matches against
   the blacklisted phrases.
2. Compressed-text detection: substring detection after space
   removal to catch spacing tricks.
3. Implicit self-harm anchors: detects self-harm terms in first-person
   context, even if not explicitly stated.
4. Risk-indicator methods: identifies methods of self-harm or risk
   actions with contextual intent (self or others).
5. Informal 'gonna <verb> myself': captures colloquial constructions
   indicating imminent self-harm.
6. Chemical or pool ingestion: detects references to ingestion or
   drowning with first-person context.
7. Human-abuse / illegal activity: flags self-referential abuse or
   confinement phrases, excluding safe contexts (e.g., "photo shoot").

Each channel adds a hit only if context and intent are plausible. The
system is deterministic, auditable, and pairs with an entirely separate feature of users
having availability to a feedback button on every page of the site.
"""

from typing import List
from .orthography import token_lemmas
import re
from difflib import SequenceMatcher
import logging

logger = logging.getLogger(__name__)

# ========================
# Crisis phrase blacklist
# ========================
_CRISIS_PHRASES = [
    "kill myself",
    "kms",
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
    "keep her in my basement",
    "keep him in my basement",
    "keep her in my crawlspace",
    "keep him in my crawlspace",
    "off myself",
    "gonna end it",
    "gonna off myself",
    "about to end it",
    "bout to off myself"
]

DEBUG = True

# ========================
# Normalization helpers
# ========================
_PUNCT_RE = re.compile(r"[^a-z0-9]+")

def normalize_text(text: str) -> str:
    return _PUNCT_RE.sub(" ", text.lower()).strip()

def compress_text(text: str) -> str:
    return normalize_text(text).replace(" ", "")

# ========================
# Contraction / colloquial normalizations
# ========================
_COLLOQUIAL_CONTRACTIONS = {
    "wanna": "want to",
    "gonna": "going to",
    "gimme": "give me",
    "lemme": "let me",
    "finna": "fixing to",
    "boutta": "about to",
    "oughtta": "want to",
    " otta ": "want to"

}

def normalize_colloquial_contractions(text: str) -> str:
    """
    Replace known contractions / colloquial terms with their canonical forms.
    Done before tokenization and morphological normalization.
    """
    def replacer(match):
        return _COLLOQUIAL_CONTRACTIONS[match.group(0)]
    
    pattern = re.compile(r'\b(' + '|'.join(map(re.escape, _COLLOQUIAL_CONTRACTIONS.keys())) + r')\b', flags=re.IGNORECASE)
    return pattern.sub(replacer, text.lower())

# ========================
# Token similarity
# ========================
def token_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

# ========================
# Morphological base forms
# ========================
_VERB_BASES = {
    "kill": {"kill", "kills", "killing", "killed"},
    "die": {"die", "dies", "dying", "died"},
    "suicide": {"suicide", "suicidal"},
    "unalive": {"unalive", "unaliving", "unalived"},
    "hang": {"hang", "hangs", "hanging", "hanged"},
    "jump": {"jump", "jumps", "jumping", "jumped"},
    "overdose": {"overdose", "overdoses", "overdosing", "overdosed"},
    "shoot": {"shoot", "shoots", "shooting", "shot"},
    "cut": {"cut", "cuts", "cutting"},
    "poison": {"poison", "poisons", "poisoning", "poisoned"},
    "drown": {"drown", "drowns", "drowning", "drowned"},
}

_MORPH_MAP = {form: base for base, forms in _VERB_BASES.items() for form in forms}

def normalize_token_morphology(token: str) -> str:
    return _MORPH_MAP.get(token, token)

# ========================
# Anchor vocabularies
# ========================
SELF_HARM_ANCHORS = {"die", "dead", "kill", "suicide", "unalive"}
RISK_INDICATOR_BASES = {"hang", "jump", "overdose", "shoot", "cut", "poison", "drown"}
SELF_REFERENT_ANCHORS = {"i", "me", "my", "myself", "life"}
THIRD_PERSON_ANCHORS = {"he", "she", "they", "him", "her", "them"}
COGNITIVE_INTENT_VERBS = {
    "think", "thinking", "thought",
    "consider", "considering",
    "planning", "plan",
    "intend", "intending",
    "want", "wanted",
    "decide", "deciding",
    "feel", "feels", "felt"
}
TEMPORAL_COMMITMENTS = {"now", "today", "tomorrow", "tonight", "soon", "later", "anymore", "never"}
REAL_WORLD_ASSERTIONS = {"did", "done", "already", "actually", "was", "were", "happened"}

HUMAN_ABUSE_ANCHORS = {"trunk", "freezer", "skin", "head", "body", "corpse", "dismember", "stash"}
CONTROL_ANCHORS = {"keep", "hold", "trap", "lock", "confine", "store", "store up"}

# ========================
# Safe / risk bigrams for ambiguous verbs
# ========================
SAFE_HANG_BIGRAMS = {
    ("hang", "out"),
    ("hang", "there"),
    ("hanging", "out"),
    ("hanging", "there"),
}

RISK_HANG_BIGRAMS = {
    ("hang", "myself"),
    ("hanging", "myself"),
}


# Placeholder for chemical ingestion vocabulary
CHEMICAL_INGESTION = {"bleach", "pills", "poison", "rat poison", "detergent"}

# ========================
# Anchor-pair check
# ========================
def anchor_pair_present(tokens: List[str]) -> bool:
    return any(t in SELF_HARM_ANCHORS for t in tokens) and any(t in SELF_REFERENT_ANCHORS for t in tokens)

# ========================
# Implicit self-reference inference
# ========================
def implicit_self_from_infinitive(tokens: List[str]) -> bool:
    for i, tok in enumerate(tokens):
        if tok in COGNITIVE_INTENT_VERBS:
            for j in range(i + 1, min(i + 4, len(tokens))):
                if tokens[j] == "to":
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

    # Normalize text, then normalize contractions
    normalized = normalize_text(text)
    normalized = normalize_colloquial_contractions(normalized)
    compressed = compress_text(normalized)

    tokens = token_lemmas(normalized)
    tokens = [normalize_token_morphology(t) for t in tokens if t]

    hits: List[str] = []

    # CHANNEL 1: token sliding-window phrase detection
    for phrase in _CRISIS_PHRASES:
        phrase_tokens = normalize_text(phrase).split()
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
                    logger.warning(f"[CRISIS DEBUG] Token match '{phrase}' via {window}")
                break

    # CHANNEL 2: compressed-text substring detection
    for phrase in _CRISIS_PHRASES:
        phrase_comp = compress_text(phrase)
        if phrase_comp in compressed:
            hits.append(phrase)
            if DEBUG:
                logger.warning(f"[CRISIS DEBUG] Compressed match '{phrase}' in '{compressed}'")

    # CHANNEL 3: implicit self-harm anchors
    for i, tok in enumerate(tokens):
        if tok in SELF_HARM_ANCHORS:
            window = tokens[max(0, i - 6): min(len(tokens), i + 7)]
            self_ref_present = any(t in SELF_REFERENT_ANCHORS for t in window) or implicit_self_from_infinitive(window)
            if self_ref_present and (any(t in TEMPORAL_COMMITMENTS for t in window) or any(t in COGNITIVE_INTENT_VERBS for t in window)):
                hits.append(f"implicit:{tok}")
                if DEBUG:
                    logger.warning(f"[CRISIS DEBUG] Implicit anchor '{tok}' with context {window}")

    # CHANNEL 4: risk-indicator detection (self or others)
    for i, tok in enumerate(tokens):
        if tok in RISK_INDICATOR_BASES:
            window = tokens[max(0, i - 7): min(len(tokens), i + 8)]

            # ------------------------
            # Bigram disambiguation for "hang"
            # ------------------------
            next_tok = tokens[i + 1] if i + 1 < len(tokens) else None
            bigram = (tok, next_tok)

            # SAFE bigram → hard ignore
            if tok == "hang" and bigram in SAFE_HANG_BIGRAMS:
                if DEBUG:
                    logger.warning(f"[CRISIS DEBUG] Safe hang bigram ignored: {bigram}")
                continue

            # RISK bigram → force elevation
            force_risk = tok == "hang" and bigram in RISK_HANG_BIGRAMS

            self_ref = (
                any(t in SELF_REFERENT_ANCHORS for t in window)
                or implicit_self_from_infinitive(window)
            )
            third_person_ref = any(t in THIRD_PERSON_ANCHORS for t in window)

            intent_or_real = (
                any(t in COGNITIVE_INTENT_VERBS for t in window)
                or any(t in TEMPORAL_COMMITMENTS for t in window)
                or any(t in REAL_WORLD_ASSERTIONS for t in window)
            )

            if force_risk or (intent_or_real and (self_ref or third_person_ref)):
                label = "risk:self" if self_ref else "risk:other"
                hits.append(f"{label}:{tok}")
                if DEBUG:
                    logger.warning(
                        f"[CRISIS DEBUG] Risk indicator '{tok}' ({label}) "
                        f"via {'bigram' if force_risk else 'context'} "
                        f"with window {window}"
                    )
                    
    # CHANNEL 5: informal / intent-based '<cognitive-verb> to <risk-action>'
    for i, tok in enumerate(tokens[:-2]):
        if tok in COGNITIVE_INTENT_VERBS and tokens[i+1] == "to":
            target_verb = tokens[i+2]
            if normalize_token_morphology(target_verb) in SELF_HARM_ANCHORS.union(RISK_INDICATOR_BASES):
                self_ref_present = any(t in SELF_REFERENT_ANCHORS for t in tokens[max(0, i-3):i+5])
                hits.append(f"intent:{target_verb}")
                if DEBUG:
                    logger.warning(f"[CRISIS DEBUG] Intent phrase detected: '{tok} {tokens[i+1]} {tokens[i+2]}' with self-ref={self_ref_present}")

    # CHANNEL 6: chemical and pool ingestion
    if any(t in CHEMICAL_INGESTION for t in tokens) and any(t in SELF_REFERENT_ANCHORS for t in tokens):
        hits.append("risk:self:chemical")
        if DEBUG:
            logger.warning(f"[CRISIS DEBUG] Chemical ingestion detected with tokens {tokens}")

    if "pool" in tokens or "backyard" in tokens:
        if any(t in SELF_REFERENT_ANCHORS for t in tokens):
            hits.append("risk:self:pool")
            if DEBUG:
                logger.warning(f"[CRISIS DEBUG] Pool drowning phrase detected with tokens {tokens}")

    # CHANNEL 7: human-abuse / illegal activity detection
    for i, tok in enumerate(tokens):
        if tok in HUMAN_ABUSE_ANCHORS:
            window = tokens[max(0, i-6): i+7]
            if any(t in CONTROL_ANCHORS for t in window) and any(t in SELF_REFERENT_ANCHORS for t in window) and not any(t in SAFE_CONTEXT for t in window):
                hits.append("risk:self:abuse")
                if DEBUG:
                    logger.warning(f"[CRISIS DEBUG] Human-abuse phrase detected with window {window}")

    return list(dict.fromkeys(hits))

# ========================
# Async crisis notification
# ========================
async def crisis_notification_async(
    text: str,
    match_threshold: float = 0.8,
    token_similarity_threshold: float = 0.85
) -> str:
    matches = await check_crisis_phrases_async(text, match_threshold, token_similarity_threshold)
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
