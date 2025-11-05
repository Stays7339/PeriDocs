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
from sentence_transformers import SentenceTransformer, util

# --- Sentence embeddings model ---
model = SentenceTransformer('all-MiniLM-L6-v2')

# --- paths ---
JOURNALS_PATH = "../data/journals.json"

# --- Load spaCy once ---
nlp = spacy.load("en_core_web_sm", disable=["parser"])
nlp.add_pipe("sentencizer")

# --- sentiment lexicons ---
_POSITIVE = {"good", "great", "happy", "relieved", "calm", "hopeful", "pleased",
             "content", "safe", "better", "improved", "relief", "grateful"}
_NEGATIVE = {"bad", "sad", "angry", "anxious", "scared", "afraid", "suicidal", "hopeless",
             "terrible", "worse", "panic", "triggered", "overwhelmed"}
_INTENSIFIERS = {"very", "extremely", "incredibly", "super", "really", "so", "utterly"}
_DEINTENSIFIERS = {"slightly", "a bit", "a little", "somewhat", "kinda", "sorta"}
_FILLERS = {"um", "uh", "like", "you know", "i guess", "i think", "sorta", "kinda"}
_COLLOQUIAL_ADD = {"bruh", "idk", "ykwim", "ong", "deadass"}
_CRISES = [
    "kill myself", "want to die", "end my life", "suicide", "can't go on",
    "tired of living", "wish i were dead", "end it all", "ultimate price", "unalive", "sewerslide"
]

# ---------- HELPERS ----------

def check_crisis_phrases(text: str) -> List[str]:
    return [p for p in _CRISES if p in text.lower()]

def crisis_notification(text: str) -> Optional[str]:
    """
    If the user entry contains high-risk phrases, return a safe notification
    and referral text instead of proceeding with normal feature extraction.
    """
    crisis_hits = check_crisis_phrases(text)
    if crisis_hits:
        return (
            "PeriDocs is not equipped to process entries describing active crises. "
            "If you feel at risk of harming yourself or others, please reach out immediately to trained professionals. "
            "In the U.S., dial 911 for emergencies or 988 for the Suicide & Crisis Lifeline. "
            "If outside the U.S., consider seeking local emergency services or visit https://www.google.com to find help."
        )
    return None

def sha_short(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]

def token_summary(doc) -> List[Dict[str, Any]]:
    return [{"text": t.text, "lemma": t.lemma_.lower(), "pos": t.pos_, "is_stop": t.is_stop} for t in doc]

# --- Sentiment heuristic updated for 0–100 scale ---
def sentiment_heuristic(doc) -> Dict[str, Any]:
    pos, neg = 0.0, 0.0
    tokens = [t.text.lower() for t in doc]
    for i, t in enumerate(tokens):
        if t in _POSITIVE:
            multiplier = 1.0
            if i > 0 and tokens[i - 1] in _INTENSIFIERS: multiplier *= 1.6
            if i > 0 and tokens[i - 1] in _DEINTENSIFIERS: multiplier *= 0.6
            if any(tok in ("not", "n't", "never") for tok in tokens[max(0, i-3):i]):
                neg += 1.0 * multiplier
            else:
                pos += 1.0 * multiplier
        elif t in _NEGATIVE:
            multiplier = 1.0
            if i > 0 and tokens[i - 1] in _INTENSIFIERS: multiplier *= 1.6
            if i > 0 and tokens[i - 1] in _DEINTENSIFIERS: multiplier *= 0.6
            if any(tok in ("not", "n't", "never") for tok in tokens[max(0, i-3):i]):
                pos += 1.0 * multiplier
            else:
                neg += 1.0 * multiplier
    raw_score = pos - neg
    # convert to 0–100 scale
    scaled_score = 50 + (raw_score * 10)
    scaled_score = max(0, min(100, scaled_score))
    bucket = "neutral"
    if scaled_score <= 49: bucket = "negative"
    elif scaled_score >= 51: bucket = "positive"
    return {"pos": pos, "neg": neg, "score": scaled_score, "bucket": bucket}

def extract_entities(doc):
    ents = [{"text": ent.text, "label": ent.label_} for ent in doc.ents]
    for t in doc:
        if t.text.lower() in _COLLOQUIAL_ADD and t.text not in [e["text"] for e in ents]:
            ents.append({"text": t.text, "label": "COLLOQUIAL"})
    return ents

def rule_paraphrase_text(doc, max_len=140) -> str:
    sents = list(doc.sents)
    if not sents: return ""
    sent_scores = []
    for sent in sents:
        sent_doc = nlp(sent.text)
        sh = sentiment_heuristic(sent_doc)
        sent_scores.append((sh["score"], sent.text))
    sent_scores.sort(key=lambda x: abs(x[0]-50), reverse=True)
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
        if last_p > 20: combined = combined[: last_p + 1]
        else: combined += "…"
    if re.search(r"\bI\b|\bI'm\b|\bI\'m\b", combined, flags=re.I):
        mirror = combined
    else:
        mirror = f"You wrote: {combined}"
    return mirror

# ---------- NEW: Repetition + Closest Match Across Entries ----------
def load_journal_embeddings() -> List[Dict[str, Any]]:
    if not os.path.exists(JOURNALS_PATH): return []
    with open(JOURNALS_PATH, "r") as f:
        try: return json.load(f)
        except json.JSONDecodeError: return []

def repetition_and_match(text: str) -> Dict[str, Any]:
    embedding = model.encode(text, convert_to_numpy=True)
    journals = load_journal_embeddings()
    if not journals: 
        return {"repetition_multiplier": 1.0, "matched_excerpt": None, "matched_source_id": None}
    embeddings = [np.array(j["embedding"]) for j in journals if "embedding" in j]
    if not embeddings: 
        return {"repetition_multiplier": 1.0, "matched_excerpt": None, "matched_source_id": None}
    sims = util.cos_sim(embedding, np.stack(embeddings))[0].cpu().numpy()
    best_idx = int(np.argmax(sims))
    best_sim = float(sims[best_idx])
    matched = journals[best_idx]
    rep_multiplier = 1.0 + best_sim
    return {
        "repetition_multiplier": rep_multiplier,
        "matched_excerpt": matched.get("paraphrase_mirror", ""),
        "matched_source_id": matched.get("sha8")
    }

# ---------- DOCUMENT FEATURES ----------
def document_features(text: str) -> Dict[str, Any]:
    # --- crisis check first ---
    crisis_msg = crisis_notification(text)
    if crisis_msg:
        return {"crisis_notification": crisis_msg}

    doc = nlp(text)
    sent = sentiment_heuristic(doc)
    ent = extract_entities(doc)
    para = rule_paraphrase_text(doc)
    rep_match = repetition_and_match(text)
    token_info = token_summary(doc)
    sentences = list(doc.sents)
    avg_sent_len = sum(len(s.text.split()) for s in sentences)/max(1,len(sentences))
    features = {
        "sha8": sha_short(text + str(time.time())),
        "tokens": token_info,
        "entities": ent,
        "sentiment_score": sent["score"],
        "sentiment_bucket": sent["bucket"],
        "paraphrase_mirror": para,
        "avg_sentence_length": avg_sent_len,
        "sentence_count": len(sentences),
        "repetition_multiplier": rep_match["repetition_multiplier"],
        "matched_excerpt": rep_match["matched_excerpt"],
        "matched_source_id": rep_match["matched_source_id"],
        "embedding": model.encode(text, convert_to_numpy=True).tolist()
    }
    return features
