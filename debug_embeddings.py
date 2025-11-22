# PeriDocs-code/debug_embeddings.py save-state from 202511211645 (date and time formatted yyyymmddhhmm)
# Note: this file allow silent fallback, which is intended for manual debugging but would hide real errors if used in production.
from core.nlp.embeddings import (
    validate_model_folder,
    load_model,
    get_embedding,
    batch_embeddings,
    model_status,
    _embedding_dim,
)
from pathlib import Path
import numpy as np
import pathlib
import sys

# ------------------ CONFIG ------------------
SNAPSHOT_BASE = "models/roberta-large/models--sentence-transformers--all-roberta-large-v1/snapshots"

def run_smoke():
    print("\n=== Model Status (before load) ===")
    print(model_status())
    print("Embedding dimension (before load):", _embedding_dim)

    # List snapshots
    snapshots = list(pathlib.Path(SNAPSHOT_BASE).iterdir())
    print("Available snapshots under:", SNAPSHOT_BASE)
    for s in snapshots:
        print(" -", s)

    # Validate model folder
    try:
        folder = validate_model_folder(Path(SNAPSHOT_BASE))
        print("\nValidated model folder:", folder)
    except Exception as e:
        print("\nModel folder validation FAILED:", e)
        print("Aborting smoke test.")
        sys.exit(2)

    # Load model
    try:
        model = load_model()
        print("\nModel loaded successfully:", type(model))
        print("Embedding dimension (after load):", _embedding_dim)
    except Exception as e:
        print("\nModel load FAILED:", e)
        print("Attempting deterministic fallback embedding check...")
        v = get_embedding("I feel happy", allow_fallback=True)
        print("Fallback embedding type/shape:", type(v), getattr(v, "shape", None), "norm:", float(np.linalg.norm(v)))
        return

    # Single embedding check
    text = "I feel very happy and excited about tomorrow."
    v = get_embedding(text, allow_fallback=False)
    print("\nSingle embedding check:")
    print("Text:", text)
    print("Type:", type(v), "Shape:", getattr(v, "shape", None), "Norm:", float(np.linalg.norm(v)))

    # Batch embedding check
    batch_texts = ["happy", "sad", "angry"]
    batch = batch_embeddings(batch_texts, allow_fallback=False)
    print("\nBatch embedding check:")
    print("Texts:", batch_texts)
    print("Batch shape:", getattr(batch, "shape", None))
    print("Per-row norms:", [float(np.linalg.norm(r)) for r in batch])

    # Check non-zero
    if np.linalg.norm(v) < 1e-6:
        print("\nWARNING: single embedding norm is near zero. Something is wrong.")
        sys.exit(3)
    print("\nSmoke test OK: embeddings non-zero.")

if __name__ == "__main__":
    run_smoke()
