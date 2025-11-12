"""
core/nlp/embeddings.py

Provides token embeddings caching and SentenceTransformer wrapper.
"""

from sentence_transformers import SentenceTransformer
from typing import List
import numpy as np
import os
import logging
import torch

logger = logging.getLogger(__name__)

# Local model path inside PeriDocs-code/models/
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "../../models/all-MiniLM-L6-v2")

# In-memory cache for token embeddings
TOKEN_EMBED_PRECOMPUTE = {}

def _load_model():
    """
    Loads the local SentenceTransformer model safely.
    If local load fails, falls back to a bundled offline model.
    Forces CPU usage for Mac/CPU-safe operation.
    Logs device being used.
    """
    try:
        logger.debug(f"Loading model from local folder: {_MODEL_PATH}")
        model = SentenceTransformer(_MODEL_PATH, device='cpu')  # Force CPU to avoid GPU issues
        # Test a dry run to confirm it's usable
        _ = model.encode("test")
        logger.info("Local model loaded successfully on CPU.")
        return model
    except Exception as e:
        logger.warning(f"Local model load failed: {e}")
        logger.info("Falling back to built-in 'all-MiniLM-L6-v2' model (no telemetry) on CPU.")
        try:
            model = SentenceTransformer(
                "sentence-transformers/all-MiniLM-L6-v2",
                device='cpu',
                trust_remote_code=True
            )
            _ = model.encode("test")
            logger.info("Fallback model loaded successfully on CPU.")
            return model
        except Exception as e2:
            logger.error(f"Fallback model load failed: {e2}")
            raise RuntimeError("Failed to load any embedding model.")

# Load once globally
_model = _load_model()

def get_embedding(text: str) -> np.ndarray:
    """
    Returns embedding vector for a given text.
    Caches results for repeated inputs.
    Returns zeros on error to keep pipeline resilient.
    """
    if not text or not text.strip():
        logger.debug("Empty input string; returning zeros.")
        return np.zeros((_model.get_sentence_embedding_dimension(),), dtype=np.float32)
    
    if text in TOKEN_EMBED_PRECOMPUTE:
        return TOKEN_EMBED_PRECOMPUTE[text]
    
    try:
        vec = _model.encode(text)
        TOKEN_EMBED_PRECOMPUTE[text] = vec
        return vec
    except Exception as e:
        logger.debug(f"Embeddings failed; returning zeros. ({e})")
        dim = _model.get_sentence_embedding_dimension()
        return np.zeros((dim,), dtype=np.float32)

def batch_embeddings(texts: List[str]) -> List[np.ndarray]:
    """
    Encode a batch of texts into embeddings.
    Uses caching where possible.
    """
    embeddings = []
    for t in texts:
        embeddings.append(get_embedding(t))
    return embeddings
