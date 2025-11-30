# test_embeddings_similarity.py
from sentence_transformers import SentenceTransformer
from numpy import dot
from numpy.linalg import norm
import numpy as np
import time

# ------------------ Stopwatch Helper ------------------
class Stopwatch:
    """Multi-faceted stopwatch for debugging"""
    def __init__(self):
        self.times = {}
        self.start_times = {}

    def start(self, label: str):
        self.start_times[label] = time.time()

    def stop(self, label: str):
        if label in self.start_times:
            elapsed = time.time() - self.start_times[label]
            self.times[label] = elapsed
            del self.start_times[label]

    def report(self):
        print("\n--- Timing Report ---")
        for label, elapsed in self.times.items():
            print(f"{label}: {elapsed:.3f} sec")
        print("---------------------\n")

# ------------------ Helper Functions ------------------
def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors"""
    return dot(a, b) / (norm(a) * norm(b))

def batch_encode_words(model, sentence: str):
    """Split sentence into words, encode all words as embeddings in one batch"""
    words = sentence.split()
    embeddings = model.encode(words, batch_size=32)
    return words, embeddings

# ------------------ Initialize Stopwatch ------------------
sw = Stopwatch()

# ------------------ Load Model ------------------
sw.start("Model loading")
print("Loading model (CPU may take ~20-30s)...")
model = SentenceTransformer("all-roberta-large-v1")
sw.stop("Model loading")
print("Model loaded.\n")

# ------------------ Define Long Test Entries ------------------
entries = [
    "I'm horribly devastated at the loss of a loved one a year ago. I have no idea what will help. I've tried everything.",
    "I feel devastated by everything that happened, from the small annoyances to the major catastrophes, like a storm sweeping through my entire life.",
    "Today I am absolutely elated and joyful. I can't stop smiling, feeling the energy coursing through me like an unstoppable river of happiness.",
    "The day has been underwhelming, mediocre at best, with everything feeling like a gray haze of nothingness and half-effort.",
    "I stumbled on the staircase and fractured my elbow, now my whole arm is throbbing painfully and I can't even lift a cup of water.",
    "I feel an overwhelming sense of anxiety creeping in every time I try to focus on work or even simple daily tasks.",
    "The breathtaking sunset filled me with wonder and awe, making me feel deeply connected to the vastness of the universe.",
    "I am furious beyond words, enraged at the injustice I’ve witnessed. Every single unfair thing keeps echoing in my mind.",
    "A bittersweet nostalgia washes over me as I remember my childhood home, its creaking floors and warm, familiar smells.",
    "I feel a dull, persistent sadness, like a cloud hanging over my head that refuses to dissipate, no matter how much I try.",
    "The chaotic noise of the city drains me completely, leaving me exhausted, overstimulated, and longing for peace."
]

# ------------------ Compute and Compare Embeddings ------------------
for i, entry in enumerate(entries, 1):
    print(f"\n--- Entry {i} ---\n{entry}\n")
    sw.start(f"Entry {i} total")

    # Sentence embedding
    sw.start(f"Entry {i} sentence embedding")
    sent_vec = model.encode(entry)
    sw.stop(f"Entry {i} sentence embedding")

    # Word embeddings in batch
    sw.start(f"Entry {i} word embeddings")
    words, word_vecs = batch_encode_words(model, entry)
    sw.stop(f"Entry {i} word embeddings")

    # Cosine similarity of each word to the full sentence
    sw.start(f"Entry {i} cosine sims")
    similarities = [cosine_sim(sent_vec, wv) for wv in word_vecs]
    sw.stop(f"Entry {i} cosine sims")

    # Print top 5 words most similar to the sentence
    top_indices = np.argsort(similarities)[::-1][:5]
    print("Top 5 words most aligned with sentence meaning:")
    for idx in top_indices:
        print(f"  {words[idx]!r}: {similarities[idx]:.3f}")

    sw.stop(f"Entry {i} total")

# ------------------ Final Report ------------------
sw.report()
print("All entries processed. Script complete.")
