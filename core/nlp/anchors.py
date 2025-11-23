"""
file: core/nlp/anchors.py

save-state updated 202511231610 (date and time formatted as follows: YYYYMMDDhhmm)

Anchors and Constants for PeriDocs NLP Pipeline
-----------------------------------------------
Filepath: core/nlp/anchors.py
Purpose:
    Centralized repository for constants, regex patterns, lexicons, and phrases
    used across PeriDocs NLP pipelines including PII redaction, emotion detection,
    crisis phrase detection, and fuzzy matching.
Functions:
    - get_emotion_anchor(emotion: str) -> set[str]
    - get_crisis_phrases() -> list[str]

Contents:
    - PII regex patterns (emails, SSNs strict/loose, phones, addresses)
    - Shared constants (COMMON_NAMES, HIGH_PROFILE_ADDRESSES)
    - Emotion lexicons (_EMOTION_LEXICONS)
    - Crisis phrases (_CRISIS_PHRASES)
    - Fillers and colloquial words (_FILLERS, _COLLOQUIAL_ADD)
"""

import re
from typing import Pattern, List, Set

# ========================
# PII Patterns
# ========================
EMAIL_PATTERN: Pattern = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
SSN_PATTERN: Pattern = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
SSN_LOOSE_PATTERN: Pattern = re.compile(r"^\d{9}$")  # bare 9 digits
PHONE_PATTERN: Pattern = re.compile(
    r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
)
ADDRESS_PATTERN: Pattern = re.compile(
    r"\d+\s+\w+(?:\s+\w+)*,\s*\w+,\s*[A-Z]{2}\s*\d{5}"
)

# ========================
# Shared constants
# ========================
COMMON_NAMES: Set[str] = {"John", "Jane", "Michael", "Emily", "Chris", "Sarah"}
HIGH_PROFILE_ADDRESSES: List[str] = ["1600 Pennsylvania Avenue NW, Washington, DC 20500"]

# ========================
# Fillers and Colloquial Words
# ========================
_FILLERS = {
    "um", "uh", "like", "you know", "i guess", "i think", "sorta", "kinda", "maybe", "literally",
    "honestly", "basically", "actually", "okay", "alright", "well", "right", "you feel me", "y’know",
    "idk", "hmm", "er", "ah", "so yeah", "anyway", "tbh", "ngl", "probs", "kinda like", "sorta like",
    "not gonna lie", "real talk", "lowkey", "highkey", "i mean", "i suppose", "i dunno", "i guess so",
    "okay so", "i was like", "he was like", "you get me", "i swear", "i’m just sayin", "ykwim", "lmao",
    "bruh", "deadass", "ong", "fr", "legit", "frrr"
}

_COLLOQUIAL_ADD = {
    "bruh", "bro", "fam", "fr", "ong", "on god", "deadass", "bet", "nah", "lmao", "lol", "smh",
    "frfr", "tf", "wtf", "damn", "ykwim", "ion", "idk", "prolly", "finna", "boutta", "gotta",
    "wanna", "tryna", "kinda", "sorta", "lowkey", "highkey", "ngl", "tbh", "no cap", "cap", "sheesh",
    "brodie", "gang", "yo", "ayo", "nah fr", "oop", "chile", "dawg", "dude", "homie", "mannn",
    "sis", "y’all", "bruv", "lmfao", "oml", "whew", "aight", "ight", "bettt", "bruhhhh", "brooo",
    "damn bro", "ong fr", "dead serious", "i’m cryin", "that’s wild", "for real", "say less"
}

# ========================
# Emotion Lexicons
# ========================
_EMOTION_LEXICONS = {
    "joy": {"happy", "joyful", "glad", "relieved", "grateful", "delighted", "ecstatic", "elated",
            "cheerful", "content", "amused", "optimistic", "radiant", "thrilled", "blissful",
            "playful", "warm", "loving", "affectionate", "appreciative", "inspired", "lighthearted",
            "peaceful", "smiling", "laughing", "carefree", "excited", "upbeat", "sunny", "serene",
            "satisfied", "rejuvenated", "comforted", "pleased", "overjoyed", "enthusiastic", "giddy", "hopeful"},
    "sadness": {"sad", "unhappy", "depressed", "lonely", "dejected", "heartbroken", "sorrowful",
                "downcast", "grieving", "melancholy", "despondent", "tearful", "wistful", "hopeless",
                "lost", "empty", "mourning", "hurt", "regretful", "remorseful", "anguished",
                "defeated", "isolated", "pained", "bereaved", "discouraged", "forlorn", "despairing",
                "weary", "pitiful", "somber", "miserable", "broken", "blue"},
    "anger": {"angry", "furious", "enraged", "livid", "pissed", "irritated", "annoyed", "aggravated",
              "hostile", "resentful", "bitter", "indignant", "mad", "wrathful", "vengeful", "fuming",
              "irate", "exasperated", "incensed", "offended", "provoked", "defiant", "fed up", "hateful",
              "combative", "argumentative", "spiteful", "belligerent", "outraged", "testy", "fiery",
              "snappy", "sour", "hostile"},
    "fear": {"scared", "afraid", "terrified", "panicked", "anxious", "alarmed", "worried", "frightened",
             "nervous", "uneasy", "tense", "cautious", "apprehensive", "jittery", "jumpy", "paranoid",
             "petrified", "horrified", "intimidated", "startled", "spooked", "distressed", "restless",
             "insecure", "shocked", "fearful", "dread-filled", "hesitant", "trembling", "shaky",
             "skittish", "sweaty-palmed"},
    "disgust": {"disgusted", "grossed out", "nauseated", "revolted", "repulsed", "sickened", "horrified",
                "appalled", "offended", "disturbed", "creeped out", "weirded out", "icky", "yucky",
                "nasty", "vile", "foul", "stinky", "filthy", "slimy", "grimy", "grotesque", "unpleasant",
                "cringe", "ew", "distasteful", "rotten", "corrupted", "tainted", "loathsome",
                "abhorrent", "detestable", "abominable"},
    "surprise": {"surprised", "shocked", "amazed", "astonished", "startled", "wowed", "impressed",
                 "stunned", "astounded", "speechless", "gobsmacked", "bewildered", "incredulous",
                 "floored", "flabbergasted", "taken aback", "caught off guard", "wide-eyed",
                 "whoa", "oof", "unbelievable", "unexpected", "out-of-nowhere", "unforeseen",
                 "spontaneous", "unpredictable", "rare", "jarring"}
}

# ========================
# Crisis phrases
# ========================
_CRISIS_PHRASES = [
    "kill myself", "want to die", "end my life", "suicide", "can't go on",
    "tired of living", "wish i were dead", "end it all", "ultimate price", "unalive", "sewerslide"
]

# ========================
# Public functions
# ========================
def get_emotion_anchor(emotion: str) -> Set[str]:
    """Return a set of anchor words for a given emotion."""
    return _EMOTION_LEXICONS.get(emotion, set())

def get_crisis_phrases() -> List[str]:
    """Return canonical list of crisis phrases for the pipeline."""
    return _CRISIS_PHRASES
