# app/nlp.py
from __future__ import annotations
import spacy
import hashlib
import math
import re
import time
from typing import Dict, List, Tuple, Any
import spacy
import numpy as np

# Load spaCy model once
nlp = spacy.load("en_core_web_sm", disable=["parser"])  # keep lightweight; enable parser if you want sentence boundaries
nlp.add_pipe("sentencizer")  # ensures sentence segmentation if parser disabled

# Small sentiment lexicon (starter; extend with domain-specific terms)
_POSITIVE = {
    "good", "great", "happy", "relieved", "calm", "hopeful", "pleased", "content",
    "safe", "safe-ish", "better", "improved", "relief", "grateful"
}
_NEGATIVE = {
    "bad", "sad", "angry", "anxious", "scared", "afraid", "suicidal", "hopeless",
    "terrible", "worse", "panic", "panicattack", "triggered", "overwhelmed"
}
_INTENSIFIERS = {"very", "extremely", "incredibly", "super", "really", "so", "utterly"}
_DEINTENSIFIERS = {"slightly", "a bit", "a little", "somewhat", "kinda", "sorta"}

# small filler words / hedges
_FILLERS = {"um", "uh", "like", "you know", "i guess", "i think", "sorta", "kinda"}

def sha_short(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def token_summary(doc) -> List[Dict[str, Any]]:
    """Return token-level data (text, lemma, pos, is_stop)."""
    return [
        {"text": t.text, "lemma": t.lemma_.lower(), "pos": t.pos_, "is_stop": t.is_stop}
        for t in doc
    ]


def repetition_score(text: str) -> float:
    """
    Heuristic: repeated words/phrases (e.g., "very very", "and and") increase a repetition penalty.
    Returns a repetition multiplier (>=1). Use to weight salience of tokens.
    """
    # collapse punctuation and lowercase
    tokens = re.findall(r"\b\w+\b", text.lower())
    if not tokens:
        return 1.0
    # count consecutive repetitions
    consec = 0
    max_consec = 0
    for a, b in zip(tokens, tokens[1:]):
        if a == b:
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 0
    # total frequency duplicates (global)
    freq = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    dup_count = sum(1 for v in freq.values() if v > 1)
    # formula: base 1.0 + (0.25 * max_consec) + (0.1 * log(1+dup_count))
    return 1.0 + (0.25 * max_consec) + (0.1 * math.log1p(dup_count))


def sentiment_heuristic(doc) -> Dict[str, Any]:
    """
    Lightweight heuristic sentiment:
      - counts positive/negative lexicon hits
      - accounts for intensifiers and de-intensifiers
      - counts negations (simple 'not', "n't" pattern) to flip sentiment
      - returns a normalized -1..+1 score and buckets (neg/neutral/pos)
    """
    pos = 0.0
    neg = 0.0
    tokens = [t.text.lower() for t in doc]
    for i, t in enumerate(tokens):
        if t in _POSITIVE:
            multiplier = 1.0
            # look back for intensifiers
            if i > 0 and tokens[i - 1] in _INTENSIFIERS:
                multiplier *= 1.6
            if i > 0 and tokens[i - 1] in _DEINTENSIFIERS:
                multiplier *= 0.6
            # check negation within 3 tokens
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
        # slight weight for exclamation-mark sentences
    # boost/penalize by repetition score: repeated distress words increase negative signal
    rep_multiplier = repetition_score(" ".join(tokens))
    # compute raw score
    raw = (pos - neg) * rep_multiplier
    # normalize to -1..1 via tanh-like squashing
    score = math.tanh(raw / 3.0)
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
    return [{"text": ent.text, "label": ent.label_} for ent in doc.ents]


# Simple paraphrase/mirror generator (rule-based)
def rule_paraphrase_text(doc, max_len=140) -> str:
    """
    Short paraphrase/mirror rule-based:
      - keep first-person perspective if present
      - compress long sentences to 1-2 lines
      - preserve emotional adjectives and intensifiers
      - remove filler hedges
      - normalize repeated intensifiers ("very very" -> "very")
    Returns a 1-2 line mirror string (not a generative LLM paraphrase).
    """
    # join sentence texts
    sents = list(doc.sents)
    if not sents:
        return ""
    # pick the 1-2 most emotionally-loaded sentences (heuristic: sentence-level sentiment)
    sent_scores = []
    for sent in sents:
        sent_doc = nlp(sent.text)  # lightweight pipeline
        sh = sentiment_heuristic(sent_doc)
        sent_scores.append((sh["score"], sent.text))
    # sort by absolute emotional score descending
    sent_scores.sort(key=lambda x: abs(x[0]), reverse=True)
    top_texts = [t for _, t in sent_scores[:2]]
    combined = " ".join(top_texts)
    # Remove filler phrases
    for f in _FILLERS:
        combined = re.sub(r"\b" + re.escape(f) + r"\b", "", combined, flags=re.I)
    # collapse repeated words like "very very very" -> "very"
    combined = re.sub(r"\b(\w+)(?:\s+\1){1,}\b", r"\1", combined, flags=re.I)
    # strip repeated punctuation
    combined = re.sub(r"([!?.,]){2,}", r"\1", combined)
    # trim whitespace, limit length
    combined = " ".join(combined.split())
    if len(combined) > max_len:
        combined = combined[: max_len - 1].rstrip()
        # cut at last sentence-like punctuation if possible
        last_p = max(combined.rfind("."), combined.rfind("!"), combined.rfind("?"))
        if last_p > 20:
            combined = combined[: last_p + 1]
        else:
            combined = combined.rstrip(" ,;:")
            combined += "…"
    # Make it a mirror line: short, present-tense, non-prescriptive
    # If text contains "I" or "I'm", preserve that phrasing; otherwise keep neutral.
    if re.search(r"\bI\b|\bI'm\b|\bI\'m\b", combined, flags=re.I):
        mirror = combined
    else:
        mirror = f"You wrote: {combined}"
    return mirror


def document_features(text: str) -> Dict[str, Any]:
    """Compute a packed set of features for an incoming journal entry."""
    doc = nlp(text)
    ent = extract_entities(doc)
    sent = sentiment_heuristic(doc)
    paraphrase = rule_paraphrase_text(doc)
    token_info = token_summary(doc)
    # a simple readability metric: average sentence length
    sentences = list(doc.sents)
    avg_sent_len = sum(len(s.text.split()) for s in sentences) / max(1, len(sentences))
    features = {
        "sha8": sha_short(text + str(time.time())),
        "tokens": token_info,
        "entities": ent,
        "sentiment": sent,
        "paraphrase_mirror": paraphrase,
        "avg_sentence_length": avg_sent_len,
        "sentence_count": len(sentences),
        "repetition_multiplier": repetition_score(text),
    }
    return features


def analyze_text(text: str):
    doc = nlp(text)
    return {
        "tokens": [token.text for token in doc],
        "entities": [(ent.text, ent.label_) for ent in doc.ents]
    }
