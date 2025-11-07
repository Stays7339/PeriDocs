# file: app/nlp.py
from __future__ import annotations
import spacy
import hashlib
import math
import re
import time
import os
import json
from typing import Dict, List, Any, Optional
import numpy as np
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

# ---------------- LEXICONS ----------------
_POSITIVE = {"good", "great", "happy", "relieved", "calm", "hopeful", "pleased",
             "content", "safe", "better", "improved", "relief", "grateful"}
_NEGATIVE = {"bad", "sad", "angry", "anxious", "scared", "afraid", "suicidal", "hopeless",
             "terrible", "worse", "panic", "triggered", "overwhelmed"}
_INTENSIFIERS = {"very", "extremely", "incredibly", "super", "really", "so", "utterly"}
_DEINTENSIFIERS = {"slightly", "a bit", "a little", "somewhat", "kinda", "sorta"}
_FILLERS = {"um", "uh", "like", "you know", "i guess", "i think", "sorta", "kinda"}
_COLLOQUIAL_ADD = {"bruh", "idk", "ykwim", "ong", "deadass"}
_CRISIS_PHRASES = [
    "kill myself", "want to die", "end my life", "suicide", "can't go on",
    "tired of living", "wish i were dead", "end it all", "ultimate price", "unalive", "sewerslide"
]

# ---------------- EMOTION LEXICONS ----------------
_EMOTION_LEXICONS = {
    "joy": {"happy", "joy", "glad", "relieved", "grateful", "pleased", "content", "hopeful", "excited"},
    "sadness": {"sad", "unhappy", "depressed", "down", "crying", "lonely", "hopeless", "heartbroken"},
    "anger": {"angry", "furious", "mad", "irritated", "annoyed", "pissed", "rage", "resentful"},
    "fear": {"scared", "afraid", "terrified", "anxious", "worried", "panicked", "fearful", "nervous"},
    "disgust": {"disgusted", "gross", "nasty", "repulsed", "sickened", "ew", "horrified"},
    "surprise": {"shocked", "amazed", "astonished", "startled", "surprised", "wow", "unexpected"}
}

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

# ---------------- PII REDACTION (with optional fuzzy matching) ----------------
def redact_pii(text: str, use_fuzzy: bool = True, threshold: int = 85) -> str:
    """
    Redact plain street addresses while leaving HIGH_PROFILE_ADDRESSES intact.
    Optionally uses fuzzy matching via rapidfuzz.
    """
    safe_text = text
    pattern = r"\d{1,5}\s[\w\s]+,?\s[\w\s]+,?\s\w{2,3}\s?\d{0,5}"
    matches = re.findall(pattern, text, flags=re.IGNORECASE)
    for match in matches:
        keep = False
        for hp in HIGH_PROFILE_ADDRESSES:
            if use_fuzzy:
                score = fuzz.ratio(match.lower(), hp.lower())
                if score >= threshold:
                    keep = True
                    break
            else:
                if match.lower() == hp.lower():
                    keep = True
                    break
        if not keep:
            safe_text = safe_text.replace(match, "[REDACTED]")
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
    """
    Returns a highly sensitive emotion + sentiment profile.
    Integrates intensifiers, negations, and repetition effects.
    """
    scores = {e: 0.0 for e in _EMOTION_LEXICONS}
    pos, neg = 0.0, 0.0
    tokens = [t.text.lower() for t in doc]

    for i, t in enumerate(tokens):
        # emotion scoring
        for emo, lex in _EMOTION_LEXICONS.items():
            if t in lex:
                multiplier = 1.0
                if i > 0 and tokens[i - 1] in _INTENSIFIERS:
                    multiplier *= 1.7
                if i > 0 and tokens[i - 1] in _DEINTENSIFIERS:
                    multiplier *= 0.6
                if any(tok in ("not", "n't", "never") for tok in tokens[max(0, i - 3):i]):
                    if emo in ("joy", "relief", "calm"):
                        scores["sadness"] += 1.0 * multiplier
                    else:
                        scores["joy"] += 0.7 * multiplier
                else:
                    scores[emo] += 1.0 * multiplier

        # general sentiment layer
        if t in _POSITIVE:
            pos += 1.0
        elif t in _NEGATIVE:
            neg += 1.0

    rep_multiplier = repetition_score(" ".join(tokens))
    for emo in scores:
        scores[emo] *= rep_multiplier

    total = sum(scores.values()) or 1.0
    norm = {k: round(v / total, 3) for k, v in scores.items()}

    raw_sentiment = (pos - neg) * rep_multiplier
    sentiment_score = math.tanh(raw_sentiment / 2.0)

    if sentiment_score <= -0.25:
        sentiment_bucket = "negative"
    elif sentiment_score >= 0.25:
        sentiment_bucket = "positive"
    else:
        sentiment_bucket = "neutral"

    return {
        "emotions": norm,
        "dominant_emotion": max(norm, key=norm.get),
        "sentiment_score": sentiment_score,
        "sentiment_bucket": sentiment_bucket,
        "repetition_multiplier": rep_multiplier,
    }

# ---------------- ENTITY EXTRACTION ----------------
def extract_entities(doc):
    ents = [{"text": ent.text, "label": ent.label_} for ent in doc.ents]
    for t in doc:
        if t.text.lower() in _COLLOQUIAL_ADD and t.text not in [e["text"] for e in ents]:
            ents.append({"text": t.text, "label": "COLLOQUIAL"})
    return ents

# ---------------- PARAPHRASE MIRROR ----------------
def rule_paraphrase_text(doc, max_len=140) -> str:
    sents = list(doc.sents)
    if not sents:
        return ""
    sent_scores = []
    for sent in sents:
        sent_doc = nlp(sent.text)
        sh = emotion_profile(sent_doc)
        sent_scores.append((abs(sh["sentiment_score"]), sent.text))
    sent_scores.sort(key=lambda x: x[0], reverse=True)
    top_texts = [t for _, t in sent_scores[:2]]
    combined = " ".join(top_texts)
    for f in _FILLERS:
        combined = re.sub(r"\b" + re.escape(f) + r"\b", "", combined, flags=re.I)
    combined = re.sub(r"\b(\w+)(?:\s+\1){1,}\b", r"\1", combined, flags=re.I)
    combined = re.sub(r"([!?.,]){2,}", r"\1", combined)
    combined = " ".join(combined.split())
    if len(combined) > max_len:
        combined = combined[: max_len - 1].rstrip()
        last_p = max(combined.rfind("."), combined.rfind("!"), combined.rfind("?"))
        if last_p > 20:
            combined = combined[: last_p + 1]
        else:
            combined = combined.rstrip(" ,;:")
            combined += "…"
    if re.search(r"\bI\b|\bI'm\b|\bI\'m\b", combined, flags=re.I):
        mirror = combined
    else:
        mirror = f"You wrote: {combined}"
    return mirror

# ---------------- DOCUMENT FEATURES ----------------
def document_features(text: str, redact_fuzzy: bool = True) -> Dict[str, Any]:
    crisis_msg = crisis_notification(text)
    if crisis_msg:
        return {"crisis_notification": crisis_msg}

    doc = nlp(text)
    emotion_data = emotion_profile(doc)
    features = {
        "sha8": hashlib.sha256((text + str(time.time())).encode("utf-8")).hexdigest()[:8],
        "tokens": token_summary(doc),
        "entities": extract_entities(doc),
        "sentiment_score": emotion_data["sentiment_score"],
        "sentiment_bucket": emotion_data["sentiment_bucket"],
        "dominant_emotion": emotion_data["dominant_emotion"],
        "emotion_distribution": emotion_data["emotions"],
        "paraphrase_mirror": rule_paraphrase_text(doc),
        "avg_sentence_length": sum(len(s.text.split()) for s in doc.sents)/max(1,len(list(doc.sents))),
        "sentence_count": len(list(doc.sents)),
        "repetition_multiplier": repetition_score(text),
        "embedding": model.encode(text, convert_to_numpy=True).tolist(),
        "safe_text": redact_pii(text, use_fuzzy=redact_fuzzy),
        "encrypted_text": encrypt_text(text)
    }
    return features

# ---------------- MODERATOR CLASSIFICATION HOOKS ----------------
MOD_CLASSIFICATIONS: Dict[str, Dict[str, Any]] = {}

def update_classification(entry_id: str, new_class: Dict[str, Any]):
    MOD_CLASSIFICATIONS[entry_id] = new_class

def get_classification(entry_id: str) -> Optional[Dict[str, Any]]:
    return MOD_CLASSIFICATIONS.get(entry_id, None)

# ---------------- TEST / EXAMPLE ----------------
if __name__ == "__main__":
    test_text = "I'm really happy but also kind of scared about what comes next!"
    features = document_features(test_text)
    print(json.dumps(features, indent=2))
