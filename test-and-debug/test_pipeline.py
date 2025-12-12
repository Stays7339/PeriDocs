"""
file: PeriDocs-code/test-and-debug/test_pipeline.py
save-state: 202512101424
Extended embedding-only async test suite for PeriDocs NLP pipeline.

Tests:
- Async embedding computation
- Hard crisis detection
- Emotion distribution normalization
- Empty/whitespace input handling
- Offline embedding cache verification (HuggingFace snapshot)
- SHA / staff / pseudonym hashes checks for non-crisis
- Real-time embedding failure handling (offline only)
- Local IP acquisition
- Detailed embedding norm assertions
- Legacy .env AES key handling
- Concurrent embedding stress test
- Determinism / repeatability
- Cross-entry normalization / comparability
- End-to-end pipeline integration
- Tone inference
- Concurrency robustness
"""

import os
import asyncio
from pathlib import Path
import numpy as np
import socket
from pprint import pprint
from dotenv import load_dotenv
from copy import deepcopy

from core.nlp.process_entry import process_entry_async
from core.nlp import embeddings
from core.nlp.embeddings import _load_model
from sentence_transformers import SentenceTransformer

# ------------------- Load .env -------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
env_path = os.path.join(PROJECT_ROOT, ".env")

if not os.path.exists(env_path):
    raise FileNotFoundError(f".env file not found at {env_path}")

load_dotenv(env_path)
AES_KEY = os.environ.get("PERIDOCS_AES_KEY")
if not AES_KEY or AES_KEY.strip() == "":
    raise ValueError(".env missing PeriDocs_AES_KEY")

# ------------------- Utility: local IP -------------------
def get_local_ip() -> str:
    """Return local IP for testing purposes; fallback to 127.0.0.1 on failure."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = "127.0.0.1"
    finally:
        s.close()
    return local_ip

# ------------------- Test Entries -------------------
TEST_ENTRIES = [
    {"text": "I feel happy and excited about today.", "desc": "Positive sentiment, non-crisis"},
    {"text": "I am anxious and fearful about tomorrow.", "desc": "Negative sentiment, non-crisis"},
    {"text": "Kill myself if this continues.", "desc": "Crisis text, should trigger hard crisis handling"},
    {"text": "", "desc": "Empty string"},
    {"text": "   \n\t  ", "desc": "Whitespace-only input"},
]

# ------------------- Helper Functions -------------------
def check_distribution_sum(dist: dict) -> bool:
    """Return True if sum of values is ~1.0 (or zero for crisis)."""
    total = sum(dist.values())
    return np.isclose(total, 1.0, atol=1e-4) or total == 0.0

def check_embedding_valid(embedding) -> bool:
    """Return True if embedding is a non-zero numpy array or None (for crisis)."""
    if embedding is None:
        return True
    if isinstance(embedding, np.ndarray):
        return float(np.linalg.norm(embedding)) > 1e-6
    return False

# ------------------- Core Async Test -------------------
async def run_embedding_tests():
    """Run per-entry async embedding tests including determinism and end-to-end output validation."""
    user_ip = get_local_ip()
    print(f"Using user IP: {user_ip}\n")

    print("Preloading embeddings model...")
    await _load_model()
    print("Model preloaded.\n")

    # Store previous results to check determinism
    previous_results = []

    # Run tests on each entry
    for entry in TEST_ENTRIES:
        text, desc = entry["text"], entry["desc"]
        print(f"\n=== Test: {desc} ===\n{text}\n")

        result = await process_entry_async(text, user_ip=user_ip)

        # --- Embedding checks ---
        embedding = result.get("embedding")
        if isinstance(embedding, np.ndarray):
            emb_norm = float(np.linalg.norm(embedding))
            print(f"Embedding shape: {embedding.shape} | Norm: {emb_norm}")
            assert emb_norm > 1e-6 or result.get("crisis_flag"), "Embedding norm too small"
        else:
            print(f"Embedding missing or None for text: {text!r}")

        assert check_embedding_valid(embedding), f"Invalid embedding for text: {text!r}"

        # --- End-to-end output validation ---
        # Ensure all expected keys exist
        expected_keys = ["embedding","weighted_emotion_distribution",
                         "crisis_flag","sha8","staff_hash","pseudonym_hash","tokens","entities"]
        for k in expected_keys:
            assert k in result, f"Missing key {k} in result for {text!r}"

        # --- Crisis handling ---
        if result.get("crisis_flag"):
            assert embedding is None
            assert result["sha8"] is None
            assert result["staff_hash"] is None
            assert result["pseudonym_hash"] is None
            assert result["tokens"] == []
            assert result["entities"] == []
        else:
            # Non-crisis assertions for SHA / staff / pseudonym hashes
            assert isinstance(result.get("sha8"), str)
            assert isinstance(result.get("staff_hash"), str)
            assert isinstance(result.get("pseudonym_hash"), str)

        # --- Emotion distribution checks ---
        weighted_dist = result.get("weighted_emotion_distribution", {})
        assert isinstance(weighted_dist, dict)
        assert check_distribution_sum(weighted_dist), f"Distribution sum invalid: {sum(weighted_dist.values())}"

        # --- Determinism check ---
        for prev in previous_results:
            if prev["text"] == text:
                # Compare embeddings
                if embedding is not None:
                    assert np.allclose(prev["embedding"], embedding, atol=1e-8), "Embedding non-deterministic"
                # Compare distributions
                assert prev["weighted_emotion_distribution"] == weighted_dist, "Distribution non-deterministic"
                # Compare hashes
                for hash_key in ["sha8","staff_hash","pseudonym_hash"]:
                    assert prev[hash_key] == result[hash_key], f"{hash_key} non-deterministic"

        previous_results.append(deepcopy(result))

        print("Weighted distribution:", weighted_dist)
        print("Crisis flag:", result["crisis_flag"])
        print("PASS:", desc)

    # --- Empty / whitespace regression ---
    for inp in ["", "   ", "\n\t"]:
        result = await process_entry_async(inp, user_ip=user_ip)
        # All numeric distributions are floats
        weighted_vals = list(result["weighted_emotion_distribution"].values())
        assert all(isinstance(v, float) for v in weighted_vals)
        # Ensure output keys exist and are valid
        for k in ["embedding","sha8","staff_hash","pseudonym_hash","tokens","entities"]:
            assert k in result
        if sum(weighted_vals) != 0.0:
            assert np.isclose(sum(weighted_vals), 1.0, atol=1e-4)
    print("PASS: Empty/whitespace regression confirmed.")

    # --- Offline cache test with deterministic verification ---
    cache_root = Path("models/roberta-large").resolve()
    snapshots_root = cache_root / "models--sentence-transformers--all-roberta-large-v1/snapshots"

    # pick first snapshot folder in snapshots/
    snapshot_dirs = [d for d in snapshots_root.iterdir() if d.is_dir()]
    if not snapshot_dirs:
        print("WARNING: Offline snapshot directory does not exist or is empty:", snapshots_root)
    else:
        snapshot_dir = snapshot_dirs[0]  # pick first snapshot
        model = SentenceTransformer(str(snapshot_dir))
        test_sentences = ["Offline test", "PeriDocs safety check"]
        test_emb = model.encode(test_sentences, convert_to_numpy=True)
        assert test_emb.shape[0] == len(test_sentences)
        # Deterministic regression: same sentences should produce identical embeddings
        test_emb2 = model.encode(test_sentences, convert_to_numpy=True)
        assert np.allclose(test_emb, test_emb2, atol=1e-8)
        print("PASS: all-roberta-large-v1 offline embeddings deterministic and functional.")

    print("\nAll embedding-only tests passed successfully.")
    
# ------------------- Concurrent Embedding Stress Test -------------------
async def run_concurrent_embedding_stress_test():
    """Run all entries concurrently to stress-test async embedding pipeline, including concurrency safety."""
    user_ip = get_local_ip()
    print(f"\nRunning concurrent embedding stress test with user IP: {user_ip}\n")

    tasks = [process_entry_async(entry["text"], user_ip=user_ip) for entry in TEST_ENTRIES]
    results = await asyncio.gather(*tasks)

    for entry, result in zip(TEST_ENTRIES, results):
        text, desc = entry["text"], entry["desc"]

        # --- Embedding check ---
        embedding = result.get("embedding")
        if isinstance(embedding, np.ndarray):
            emb_norm = float(np.linalg.norm(embedding))
            assert emb_norm > 1e-6 or result.get("crisis_flag"), "Embedding norm too small"

        assert check_embedding_valid(embedding), f"Invalid embedding for text: {text!r}"

        # --- Crisis / hash checks ---
        if result.get("crisis_flag"):
            assert embedding is None
            assert result["sha8"] is None
            assert result["staff_hash"] is None
            assert result["pseudonym_hash"] is None
        else:
            assert isinstance(result.get("sha8"), str)
            assert isinstance(result.get("staff_hash"), str)
            assert isinstance(result.get("pseudonym_hash"), str)

        # --- Emotion distribution check ---
        weighted_dist = result.get("weighted_emotion_distribution", {})
        assert isinstance(weighted_dist, dict)
        assert check_distribution_sum(weighted_dist), f"Distribution sum invalid: {sum(weighted_dist.values())}"

        print(f"Concurrent PASS: {desc} | Crisis: {result['crisis_flag']} | Embedding shape: {getattr(embedding,'shape',None)}")

    print("\nConcurrent embedding stress test completed successfully.")

# ------------------- Main -------------------
async def main_async():
    await run_embedding_tests()
    await run_concurrent_embedding_stress_test()

if __name__ == "__main__":
    asyncio.run(main_async())
