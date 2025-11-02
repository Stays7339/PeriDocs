# app/nlp.py
from __future__ import annotations
import spacy
import hashlib
import math
import re
import time
import os
import json
from typing import Dict, List, Any
import numpy as np
from sentence_transformers import SentenceTransformer, util
import torch

# --- Sentence embeddings model (for semantic similarity + typo tolerance) ---
model = SentenceTransformer('all-MiniLM-L6-v2')

# --- paths ---
JOURNALS_PATH = "../data/journals.json"

# --- Load spaCy model once ---
nlp = spacy.load("en_core_web_sm", disable=["parser"])
nlp.add_pipe("sentencizer")

# --- sentiment and emotional lexicons ---
_POSITIVE = {
    "good", "great", "happy", "relieved", "calm", "hopeful", "pleased",
    "content", "safe", "better", "improved", "relief", "grateful"
}
_NEGATIVE = {
    "bad", "sad", "angry", "anxious", "scared", "afraid", "suicidal", "hopeless",
    "terrible", "worse", "panic", "triggered", "overwhelmed"
}
_CRISES = [
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
_INTENSIFIERS = {"very", "extremely", "incredibly", "super", "really", "so", "utterly"}
_DEINTENSIFIERS = {"slightly", "a bit", "a little", "somewhat", "kinda", "sorta"}
_FILLERS = {"um", "uh", "like", "you know", "i guess", "i think", "sorta", "kinda"}
_COLLOQUIAL_ADD = {"bruh", "idk", "ykwim", "ong", "deadass"}

# ---------- CORE HELPERS ----------

def check_crisis_phrases(text: str) -> List[str]:
    return [p for p in _CRISES if p in text.lower()]

def sha_short(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]

def token_summary(doc) -> List[Dict[str, Any]]:
    return [
        {"text": t.text, "lemma": t.lemma_.lower(), "pos": t.pos_, "is_stop": t.is_stop}
        for t in doc
    ]

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

def sentiment_heuristic(doc) -> Dict[str, Any]:
    pos = 0.0
    neg = 0.0
    tokens = [t.text.lower() for t in doc]
    for i, t in enumerate(tokens):
        if t in _POSITIVE:
            multiplier = 1.0
            if i > 0 and tokens[i - 1] in _INTENSIFIERS:
                multiplier *= 1.6
            if i > 0 and tokens[i - 1] in _DEINTENSIFIERS:
                multiplier *= 0.6
            if any(tok in ("not", "n't", "never") for tok in tokens[max(0, i - 3):i]):
                neg += 1.0 * multiplier
            else:
                pos += 1.0 * multiplier
        elif t in _NEGATIVE:
            multiplier = 1.0
            if i > 0 and tokens[i - 1] in _INTENSIFIERS:
                multiplier *= 1.6
            if i > 0 and tokens[i - 1] in _DEINTENSIFIERS:
                multiplier *= 0.6
            if any(tok in ("not", "n't", "never") for tok in tokens[max(0, i - 3):i]):
                pos += 1.0 * multiplier
            else:
                neg += 1.0 * multiplier
    rep_multiplier = repetition_score(" ".join(tokens))
    raw = (pos - neg) * rep_multiplier
    score = math.tanh(raw / 3.0)  # scaled to [-1,1]
    bucket = "neutral"
    if score <= -0.3:
        bucket = "negative"
    elif score >= 0.3:
        bucket = "positive"
    return {
        "pos": pos,
        "neg": neg,
        "repetition_multiplier": rep_multiplier,
        "score": score,
        "bucket": bucket,
    }

def extract_entities(doc):
    ents = [{"text": ent.text, "label": ent.label_} for ent in doc.ents]
    # include colloquial markers as pseudo-entities
    for t in doc:
        if t.text.lower() in _COLLOQUIAL_ADD and t.text not in [e["text"] for e in ents]:
            ents.append({"text": t.text, "label": "COLLOQUIAL"})
    return ents

def rule_paraphrase_text(doc, max_len=140) -> str:
    sents = list(doc.sents)
    if not sents:
        return ""
    sent_scores = []
    for sent in sents:
        sent_doc = nlp(sent.text)
        sh = sentiment_heuristic(sent_doc)
        sent_scores.append((sh["score"], sent.text))
    sent_scores.sort(key=lambda x: abs(x[0]), reverse=True)
    top_texts = [t for _, t in sent_scores[:2]]
    combined = " ".join(top_texts)
    # remove filler words
    for f in _FILLERS:
        combined = re.sub(r"\b" + re.escape(f) + r"\b", "", combined, flags=re.I)
    # remove consecutive repeated words
    combined = re.sub(r"\b(\w+)(?:\s+\1){1,}\b", r"\1", combined, flags=re.I)
    # remove repeated punctuation
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

def document_features(text: str) -> Dict[str, Any]:
    doc = nlp(text)
    ent = extract_entities(doc)
    sent = sentiment_heuristic(doc)
    paraphrase = rule_paraphrase_text(doc)
    token_info = token_summary(doc)
    sentences = list(doc.sents)
    avg_sent_len = sum(len(s.text.split()) for s in sentences) / max(1, len(sentences))
    # embedding for semantic similarity / typo-tolerance
    embedding = model.encode(text, convert_to_numpy=True).tolist()
    features = {
        "sha8": sha_short(text + str(time.time())),
        "tokens": token_info,
        "entities": ent,
        "sentiment": sent,
        "paraphrase_mirror": paraphrase,
        "avg_sentence_length": avg_sent_len,
        "sentence_count": len(sentences),
        "repetition_multiplier": repetition_score(text),
        "embedding": embedding
    }
    return features

# ---------- MAIN RUN FOR TESTING ----------
if __name__ == "__main__":
    test_text = "I wanna kill myself"
    crisis_hits = check_crisis_phrases(test_text)
    print("Saving journals.json to:", os.path.abspath(JOURNALS_PATH))
    if crisis_hits:
        print(f"⚠️ CRISIS DETECTED: High-risk phrases found: {crisis_hits}")
        print("Entry not saved automatically.")
    else:
        features = document_features(test_text)
        data = []
        if os.path.exists(JOURNALS_PATH):
            with open(JOURNALS_PATH, "r") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = []
        data.append(features)
        with open(JOURNALS_PATH, "w") as f:
            json.dump(data, f, indent=2)
        print("Entries to write:", len(data))
        print("Last entry features:", features)
