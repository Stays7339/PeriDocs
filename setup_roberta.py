#!/usr/bin/env python3
"""
PeriDocs setup script for all-roberta-large-v1 SentenceTransformer.

- Creates models/roberta-large folder if missing
- Pre-downloads the model if needed
- Forces offline mode to avoid telemetry
- Works from any current working directory
"""

import os
from pathlib import Path
from sentence_transformers import SentenceTransformer

# ------------------ Paths ------------------
PROJECT_ROOT = Path(__file__).parent.resolve()
MODEL_FOLDER = PROJECT_ROOT / "models" / "roberta-large"

# Create folder if missing
MODEL_FOLDER.mkdir(parents=True, exist_ok=True)

# ------------------ Force offline ------------------
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

# ------------------ Download / Load model ------------------
try:
    print(f"Loading SentenceTransformer model into {MODEL_FOLDER}...")
    model = SentenceTransformer(
        "all-roberta-large-v1",
        cache_folder=str(MODEL_FOLDER)
    )
    print("Model loaded successfully.")
    # Test embedding
    test_emb = model.encode("Hello world", convert_to_numpy=True, normalize_embeddings=True)
    print(f"Test embedding shape: {test_emb.shape}")
except Exception as e:
    print(f"Error loading model: {e}")
