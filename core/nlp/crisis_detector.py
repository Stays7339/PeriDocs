"""
core/nlp/crisis_detector.py
save-state updated 202512111413

Self-contained async crisis detection module for PeriDocs.
- Detects crisis phrases in user text.
- Returns alerts / notifications if phrases are found.
- Fully async-safe (no blocking wrappers).
"""

from typing import List
import asyncio

# ========================
# Crisis phrases (canonical, static)
# ========================
_CRISIS_PHRASES = [
    # Direct expressions of suicidal / homicidal / self-harm intent
    "i want to die",
    "i want to kill myself",
    "i want to end my life",
    "i'm going to kill myself",
    "i'm going to end it",
    "end my life",
    "kill myself",
    "take my own life",
    "end it all",
    "end everything",
    "i'm done living",
    "pull the trigger",
    "stab",
    "drown",
    "rope",
    "noose",
    "hang myself",
    "overdose",
    "take a full bottle",
    "swallow a full bottle",
    "drink a full bottle",
    "take an entire bottle",
    "swallow an entire bottle",
    "drink an entire bottle",
    "take the entire bottle",
    "swallow the entire bottle",
    "drink the entire bottle",
    "I don't think i can get better",
    "I don't think I'm capable of getting better",
    "I dont think im capable of getting better",
    

    # Preparatory / imminence signals
    "tonight i'm ending it",
    "this is my last day",
    "i won't be here tomorrow",
    "i'm saying goodbye",
    "i'm planning to end it",
    "i already wrote a note",
    "i made my decision to end it",

    # Strong ideation signals
    "thinking about killing myself",
    "thinking about ending it all",
    "i keep imagining my death",
    "i've been thinking about suicide",
    "i'm considering suicide",

    # Common online shorthand / euphemisms (self-directed only)
    "kys",
    "kms",
    "unalive myself",
    "unalive me",
    "sewerslide",
    "suicide",
    "Su1c1d3",
    "5u1c1d3",
    "5u1c1de",
    "end myself",
    "do the final act",
    "pay the ultimate price",  # keep original
    "ultimate price",

    # Requests for method discussion
    "how to kill myself",
    "how to end my life",
    "best way to die",
    "painless ways to die",
    "fastest way to kill myself",

    # Entrenched intent phrasing
    "i can't keep myself safe",
    "i don't trust myself to stay alive",
    "i think i'm going to do something dangerous",
    "i can't stop thinking about ending it",
]


# ========================
# Async Detection Functions
# ========================
async def check_crisis_phrases(text: str) -> List[str]:
    """Return crisis phrases found in text, case-insensitive."""
    if not text:
        return []
    # For large inputs, simulate async chunking
    text_lower = text.lower()
    matches: List[str] = []
    for phrase in _CRISIS_PHRASES:
        if phrase in text_lower:
            matches.append(phrase)
        # Yield control to the event loop for very large texts
        await asyncio.sleep(0)
    return matches

async def crisis_notification(text: str) -> str:
    """Return standardized warning message if crisis phrases are detected."""
    matches = await check_crisis_phrases(text)
    if not matches:
        return ""
    return (
        "⚠️ Your writing suggests the possibility of emotional or mental health strain. "
        "There are professionals and services outside of PeriDocs equipped to provide guidance."
    )