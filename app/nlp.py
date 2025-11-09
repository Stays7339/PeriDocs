# file: app/nlp.py
from __future__ import annotations
import spacy
import hashlib
import numpy as np
import math
import re
import time
import os
import json
from typing import Dict, List, Any, Optional
from sentence_transformers import SentenceTransformer
from cryptography.fernet import Fernet
from rapidfuzz import fuzz
from dotenv import load_dotenv

# ---------------- ENV & MODEL SETUP ----------------
load_dotenv()  # load PERIDOCS_AES_KEY from .env
AES_KEY = os.environ.get("PERIDOCS_AES_KEY")
if not AES_KEY:
    raise RuntimeError("PERIDOCS_AES_KEY env variable not set")
fernet = Fernet(AES_KEY)

model = SentenceTransformer('all-MiniLM-L6-v2')

# ---------------- FILE PATHS ----------------
JOURNALS_PATH = "../data/journals.json"
HIGH_PROFILE_PATH = "../data/high_profile_addresses.json"

# ---------------- spaCy SETUP ----------------
nlp = spacy.load("en_core_web_sm", disable=["parser"])
nlp.add_pipe("sentencizer")

# ---------------- COMMON NAMES / PII PATTERNS ----------------
COMMON_NAMES = {"John", "Jane", "Michael", "Emily", "Chris", "Sarah"}  # minimal example
EMAIL_PATTERN = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
SSN_PATTERN = r'\b\d{3}-\d{2}-\d{4}\b'
PHONE_PATTERN = r'\b(?:\+?1[-.\s]?|)(?:\(?\d{3}\)?[-.\s]?){2}\d{4}\b'
ADDRESS_PATTERN = r'\b\d{1,5}\s\w+(?:\s\w+){0,5}\b'  # crude placeholder

# ---------------- LEXICONS ----------------
_POSITIVE = {
    "good", "great", "wonderful", "lovely", "amazing", "awesome", "fantastic", "excellent", 
    "superb", "splendid", "brilliant", "delightful", "cheerful", "upbeat", "optimistic", 
    "hopeful", "serene", "peaceful", "satisfied", "fulfilled", "grateful", "thankful", "blessed", 
    "comfortable", "secure", "proud", "inspired", "motivated", "driven", "confident", "assured", 
    "certain", "accomplished", "relieved", "happy", "joyful", "elated", "ecstatic", "thrilled", 
    "overjoyed", "pleased", "content", "calm", "chill", "easygoing", "stable", "flourishing", 
    "thriving", "empowered", "liberated", "relaxed", "balanced", "soothed", "touched", "moved", 
    "affectionate", "loving", "caring", "kind", "compassionate", "generous", "open", "honest", 
    "real", "authentic", "grounded", "centered", "trusting", "enthusiastic", "eager", "determined", 
    "bold", "daring", "fearless", "excited", "energized", "awake", "alive", "present", "mindful", 
    "patient", "forgiving", "gentle", "wise", "capable", "resilient", "adaptable", "creative", 
    "innovative", "visionary", "harmonious", "vibrant", "radiant", "glowing", "self-assured", 
    "peaceful"
}

_NEGATIVE = {
    "bad", "awful", "terrible", "horrible", "dreadful", "depressing", "sad", "sorrowful", "hopeless", 
    "helpless", "miserable", "worthless", "guilty", "ashamed", "embarrassed", "humiliated", 
    "angry", "furious", "enraged", "bitter", "resentful", "jealous", "envious", "hateful", 
    "spiteful", "scared", "frightened", "terrified", "panicked", "anxious", "uneasy", "nervous", 
    "tense", "stressed", "overwhelmed", "burdened", "exhausted", "drained", "tired", "fatigued", 
    "restless", "broken", "shattered", "ruined", "devastated", "heartbroken", "lonely", 
    "isolated", "rejected", "neglected", "ignored", "unseen", "unheard", "unloved", 
    "unsafe", "insecure", "uncertain", "doubtful", "regretful", "remorseful", "lost", "confused", 
    "stuck", "trapped", "powerless", "weak", "vulnerable", "fragile", "unstable", "jittery", 
    "jumpy", "paranoid", "disgusted", "grossed out", "revolted", "nauseated", "sickened", 
    "horrified", "appalled", "disturbed", "irritated", "annoyed", "agitated", "offended", 
    "disrespected", "betrayed", "suffocated", "constricted", "anxious", "suicidal", "despairing"
}

_INTENSIFIERS = {
    "very", "extremely", "really", "super", "mega", "ultra", "hella", "wicked", "mad", "damn", 
    "totally", "absolutely", "completely", "entirely", "wholly", "thoroughly", "purely", 
    "incredibly", "seriously", "ridiculously", "insanely", "wildly", "crazily", "tremendously", 
    "vastly", "extraordinarily", "phenomenally", "beyond", "especially", "overwhelmingly", 
    "intensely", "powerfully", "deeply", "so", "heaping", "freaking", "absurdly", "notably", 
    "strikingly", "severely", "exponentially", "monumentally", "outlandishly", "excessively", 
    "passionately", "strongly", "mightily"
}

_DEINTENSIFIERS = {
    "slightly", "somewhat", "kind of", "sort of", "a little", "a bit", "barely", "hardly", 
    "mildly", "faintly", "loosely", "gently", "modestly", "softly", "quietly", "weakly", "thinly", 
    "tenuously", "partially", "incompletely", "fractionally", "semi", "quasi", "not really", 
    "not much", "only a little", "just a touch", "halfway", "tepidly", "limply", "almost", 
    "nearly", "practically", "virtually", "kindasorta", "lowkey", "vaguely", "barely-there", 
    "meh", "subduedly", "temperedly", "cautiously", "lightly", "marginally", "minutely", 
    "slowly", "hesitantly", "passably"
}

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

_CRISIS_PHRASES = [
    "kill myself", "want to die", "end my life", "suicide", "can't go on",
    "tired of living", "wish i were dead", "end it all", "ultimate price", "unalive", "sewerslide"
]

# ---------------- EMOTION LEXICONS ----------------
_EMOTION_LEXICONS = {
    "joy": {"happy", "joyful", "glad", "relieved", "grateful", "delighted", "ecstatic", "elated", 
            "cheerful", "content", "amused", "optimistic", "radiant", "thrilled", "blissful", 
            "playful", "warm", "loving", "affectionate", "appreciative", "inspired", "lighthearted", 
            "peaceful", "smiling", "laughing", "carefree", "excited", "upbeat", "sunny", "serene", 
            "satisfied", "rejuvenated", "comforted", "pleased", "overjoyed", "enthusiastic", "giddy", "radiant"},
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
                 "floored", "flabbergasted", "taken aback", "caught off guard", "wide-eyed", "amazed", 
                 "whoa", "oof", "unbelievable", "unexpected", "out-of-nowhere", "unforeseen", 
                 "spontaneous", "unpredictable", "rare", "jarring"}
}

# ---------------- SENTIMENT SCORE ----------------

def sentiment_label(score: float) -> str:
    """Convert a -1.0–1.0 sentiment score to a textual label"""
    if score >= 0.6:
        return "very positive"
    elif score >= 0.2:
        return "positive"
    elif score > -0.2:
        return "neutral"
    elif score > -0.6:
        return "negative"
    else:
        return "very negative"

# ---------------- PRECOMPUTE TOKEN EMBEDDINGS ----------------
TOKEN_EMBED_PRECOMPUTE: Dict[str, np.ndarray] = {}
all_tokens_for_lookup = set().union(
    *_EMOTION_LEXICONS.values(), _POSITIVE, _NEGATIVE, _INTENSIFIERS, _DEINTENSIFIERS
)
for tok in all_tokens_for_lookup:
    TOKEN_EMBED_PRECOMPUTE[tok] = model.encode(tok, convert_to_numpy=True)

# ---------------- HIGH-PROFILE ADDRESSES ----------------
if os.path.exists(HIGH_PROFILE_PATH):
    with open(HIGH_PROFILE_PATH, "r") as f:
        HIGH_PROFILE_ADDRESSES = json.load(f)
else:
    HIGH_PROFILE_ADDRESSES = []

# ---------------- ENCRYPTION ----------------
def encrypt_text(text: str) -> str:
    return fernet.encrypt(text.encode("utf-8")).decode("utf-8")

def decrypt_text(ciphertext: str) -> str:
    return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")

# ---------------- PII REDACTION ----------------
def redact_pii(text: str, use_fuzzy: bool = True, threshold: int = 85) -> str:
    safe_text = text
    safe_text = re.sub(EMAIL_PATTERN, '[EMAIL]', safe_text)
    safe_text = re.sub(SSN_PATTERN, '[SSN]', safe_text)
    safe_text = re.sub(PHONE_PATTERN, '[PHONE]', safe_text)

    matches = re.findall(ADDRESS_PATTERN, safe_text, flags=re.IGNORECASE)
    for match in matches:
        keep = False
        for hp in HIGH_PROFILE_ADDRESSES:
            if use_fuzzy and fuzz.ratio(match.lower(), hp.lower()) >= threshold:
                keep = True
                break
            elif not use_fuzzy and match.lower() == hp.lower():
                keep = True
                break
        if not keep:
            safe_text = safe_text.replace(match, '[ADDRESS]')

    doc = nlp(safe_text)
    spans = []

    for ent in doc.ents:
        if ent.label_ == "PERSON":
            for w in ent.text.split():
                if w.lower() not in COMMON_NAMES:
                    for match_obj in re.finditer(rf'\b{re.escape(w)}\b', safe_text):
                        spans.append((match_obj.start(), match_obj.end()))

    words = safe_text.split()
    for w in words:
        clean_word = re.sub(r'\W+', '', w)
        if clean_word.istitle() and clean_word.lower() not in COMMON_NAMES:
            for match_obj in re.finditer(rf'\b{re.escape(clean_word)}\b', safe_text):
                spans.append((match_obj.start(), match_obj.end()))

    for start, end in sorted(spans, reverse=True):
        safe_text = safe_text[:start] + '[NAME]' + safe_text[end:]

    return safe_text

# ---------------- CRISIS DETECTION ----------------
def check_crisis_phrases(text: str) -> List[str]:
    return [p for p in _CRISIS_PHRASES if p in text.lower()]

def crisis_notification(text: str) -> Optional[str]:
    hits = check_crisis_phrases(text)
    if hits:
        return (
            "PeriDocs is not equipped to process entries describing active crises. "
            "If you feel at risk of harming yourself or others, please reach out immediately. "
            "In the U.S., dial 911 for emergencies or 988 for the Suicide & Crisis Lifeline. "
            "Elsewhere, seek local emergency services."
        )
    return None

# ---------------- TOKENIZATION ----------------
def token_summary(doc) -> List[Dict[str, Any]]:
    return [{"text": t.text, "lemma": t.lemma_.lower(), "pos": t.pos_, "is_stop": t.is_stop} for t in doc]

# ---------------- REPETITION / ECHO WEIGHTING ----------------
def repetition_score(text: str) -> float:
    tokens = re.findall(r"\b\w+\b", text.lower())
    if not tokens:
        return 1.0
    consec = 0
    max_consec = 0
    for a, b in zip(tokens, tokens[1:]):
        if a == b:
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 0
    freq = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    dup_count = sum(1 for v in freq.values() if v > 1)
    return 1.0 + (0.25 * max_consec) + (0.1 * math.log1p(dup_count))

# ---------------- EMOTION-AWARE SENTIMENT ----------------
def emotion_profile(doc) -> Dict[str, Any]:
    scores = {e: 0.0 for e in _EMOTION_LEXICONS}
    pos, neg = 0.0, 0.0
    tokens = [t.text.lower() for t in doc]

    for i, t in enumerate(tokens):
        if t in TOKEN_EMBED_PRECOMPUTE:
            tok_emb = TOKEN_EMBED_PRECOMPUTE[t]
        else:
            tok_emb = model.encode(t, convert_to_numpy=True)
            TOKEN_EMBED_PRECOMPUTE[t] = tok_emb

        intensity = 1.0
        if i > 0:
            if tokens[i - 1] in _INTENSIFIERS:
                intensity *= 1.5
            elif tokens[i - 1] in _DEINTENSIFIERS:
                intensity *= 0.5

        for emotion, lex in _EMOTION_LEXICONS.items():
            if lex:  # ensure non-empty
                sim = np.dot(tok_emb, np.mean([TOKEN_EMBED_PRECOMPUTE[w] for w in lex], axis=0))
                scores[emotion] += sim * intensity

        if t in _POSITIVE:
            pos += intensity
        elif t in _NEGATIVE:
            neg += intensity

    return {"raw_scores": scores, "valence": pos - neg, "arousal": pos + neg}

# ---------------- MAIN PROCESSING ----------------
def process_entry(text: str) -> Dict[str, Any]:
    crisis_msg = crisis_notification(text)
    if crisis_msg:
        return {"crisis_warning": crisis_msg}

    safe_text = redact_pii(text)
    encrypted_text = encrypt_text(text)
    doc = nlp(safe_text)
    tokens = token_summary(doc)
    repetition = repetition_score(safe_text)
    embedding = model.encode(safe_text, convert_to_numpy=True)
    entities = [{"text": ent.text, "label": ent.label_} for ent in doc.ents] if doc.ents else []
    emotions = emotion_profile(doc)
    sha8 = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]

    return {
        "sha8": sha8,
        "encrypted_text": encrypted_text,
        "safe_text": safe_text,
        "tokens": tokens,
        "entities": entities,
        "embedding": embedding.tolist() if embedding is not None else [],
        "repetition_multiplier": repetition,
        "emotions": emotions
    }

# ---------------- DOCUMENT FEATURES ----------------
def _json_safe(obj):
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    elif isinstance(obj, (np.float32, np.float64, np.int32, np.int64)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return _json_safe(obj.tolist())
    else:
        return obj

def document_features(text: str) -> Dict[str, Any]:
    safe_text = redact_pii(text)
    encrypted_text = encrypt_text(text)
    sha8 = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]

    doc = nlp(safe_text)
    tokens = token_summary(doc)
    repetition = repetition_score(safe_text)
    embedding = model.encode(safe_text, convert_to_numpy=True)
    entities = [{"text": ent.text, "label": ent.label_} for ent in doc.ents] if doc.ents else []
    emotions = emotion_profile(doc)
    dominant_emotion = max(emotions["raw_scores"], key=emotions["raw_scores"].get) if emotions["raw_scores"] else "unknown"
    valence = emotions["valence"]
    sentiment_score = max(-1.0, min(1.0, valence / 10.0))
    sentiment_bucket = sentiment_label(sentiment_score)
    sentences = list(doc.sents)
    avg_sentence_length = sum(len(s.text.split()) for s in sentences) / max(1, len(sentences))

    features = {
        "sha8": sha8,
        "encrypted_text": encrypted_text,
        "safe_text": safe_text,
        "sentiment_score": sentiment_score,
        "sentiment_bucket": sentiment_bucket,
        "dominant_emotion": dominant_emotion,
        "emotion_distribution": emotions["raw_scores"],
        "paraphrase_mirror": "",
        "avg_sentence_length": avg_sentence_length,
        "sentence_count": len(sentences),
        "repetition_multiplier": repetition,
        "embedding": embedding.tolist() if embedding is not None else [],
        "entities": entities,
        "tokens": tokens
    }

    return _json_safe(features)
