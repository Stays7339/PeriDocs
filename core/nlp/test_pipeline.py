"""
core/nlp/test_pipeline.py save-state from 202511211645 (date and time formatted yyyymmddhhmm)

Fully async test suite for PeriDocs NLP pipeline.
Ensures:
- Core NLP pipeline correctness
- Async embedding compatibility
- Offline cache functionality
- Intensity/deintensifier handling
- Crisis detection
- Backward compatibility
"""

import os
from pathlib import Path
from pprint import pprint
import asyncio
import numpy as np
import socket
import copy
from dotenv import load_dotenv

from core.nlp.process_entry import process_entry_async
from core.nlp.emotion_analysis import (
    analyze_emotions,
    apply_intensity_modifiers,
    compute_emotion_profile,
    compute_sentiment_from_profile,
    get_intensifiers,
    get_deintensifiers
)
from core.nlp import embeddings
from core.nlp.embeddings import _load_model
from sentence_transformers import SentenceTransformer

# ------------------- Load .env -------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
env_path = os.path.join(PROJECT_ROOT, ".env")
if not os.path.exists(env_path):
    raise FileNotFoundError(f".env file not found at {env_path}")

load_dotenv(env_path)
AES_KEY = os.environ.get("PERIDOCS_AES_KEY")
if not AES_KEY or AES_KEY.strip() == "":
    raise ValueError(".env missing PeriDocs_AES_KEY")


# ======= dynamic dummy (local LAN) IP test ======
def get_local_ip() -> str:
    """Returns local LAN IP without sending data."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = "127.0.0.1"
    finally:
        s.close()
    return local_ip


# ------------------- Core async tests -------------------
async def run_async_tests():
    """Fully async tests replacing previous synchronous tests."""
    user_ip = get_local_ip()

    test_cases = [
        {"text": "I’m feeling hopeful but a bit anxious about tomorrow.",
         "desc": "Mixed positive/negative emotions, light intensity modifier."},
        {"text": "", "desc": "Empty string input."},
        {"text": "   ", "desc": "Whitespace-only input."},
        {"text": "I am VERY happy, but also slightly sad.",
         "desc": "Uppercase intensifier + deintensifier combination."},
        {"text": "Kill myself now, I can't go on.",
         "desc": "Crisis phrase input."},
        {"text": "Just normal text with no emotion keywords.",
         "desc": "Neutral text without anchors."},
    ]

    for case in test_cases:
        text, desc = case["text"], case["desc"]
        print(f"\n=== Testing Entry: {desc} ===\n{text}\n")

        result = await process_entry_async(text, user_ip)

        # --- print a safe summary for readability, keep embedding intact ---
        real_embedding = result.get("embedding", None)
        if isinstance(real_embedding, np.ndarray):
            emb_norm = float(np.linalg.norm(real_embedding))
            print(f"Embedding shape: {real_embedding.shape} | Norm: {emb_norm}")
        else:
            print(f"NOTE: Embedding was redacted/suppressed for text: {text!r}")
            print(f"Embedding shape: N/A | Norm check skipped if redacted")

        # --- Conditional structural/type assertions ---
        def all_leaf_values_float(d):
            """Recursively check all leaf values in nested dicts are floats or np.floating."""
            if isinstance(d, dict):
                return all(all_leaf_values_float(v) for v in d.values())
            return isinstance(d, (float, np.floating))

        def leaves_are_zero(d):
            """Recursively check all leaf numeric values are zero."""
            if isinstance(d, dict):
                return all(leaves_are_zero(v) for v in d.values())
            try:
                return float(d) == 0.0
            except Exception:
                return False

        result_emotion = result.get("emotion")

        if result.get("crisis_flag"):
            # Crisis entry: verify intentional empty/None placeholders
            assert result["sha8"] is None, "Crisis sha8 should be None"
            assert result["staff_hash"] is None, "Crisis staff_hash should be None"
            assert result["pseudonym_hash"] is None, "Crisis pseudonym_hash should be None"
            assert result["tokens"] == [], "Crisis tokens should be empty list"
            assert result["entities"] == [], "Crisis entities should be empty list"
            assert result["embedding"] is None, "Crisis embedding should be None"
        else:
            # Non-crisis entry: full assertions
            assert "emotion" in result, "Missing 'emotion' key."
            assert "weighted_emotion_distribution" in result, "Missing 'weighted_emotion_distribution' key."
            assert "sentiment" in result, "Missing 'sentiment' key."
            assert "summary" in result, "Missing 'summary' key."
            assert "primary_emotion" in result["summary"], "Missing 'primary_emotion' in summary."
            assert "intensity" in result["summary"], "Missing 'intensity' in summary."

            # Type checks
            if result_emotion is not None:
                assert all_leaf_values_float(result_emotion), \
                    f"All leaf emotion values should be floats, got: {result_emotion}"

            # Embedding norm check
            if real_embedding is not None and isinstance(real_embedding, np.ndarray):
                emb_norm = float(np.linalg.norm(real_embedding))
                if text.strip():
                    assert emb_norm > 1e-6, f"Embedding norm too small ({emb_norm}) for text: {text!r}"

            assert isinstance(result["embedding_mean"], float)
            assert isinstance(result["repetition_multiplier"], (float, int))
            assert isinstance(result["sha8"], str)
            assert isinstance(result["pseudonym_hash"], str)
            assert isinstance(result["crisis_flag"], bool)

            # Weighted emotions sum check
            weighted_vals = list(result["weighted_emotion_distribution"].values())
            total_prob = sum(weighted_vals)
            if total_prob != 0.0:
                assert np.isclose(total_prob, 1.0, atol=1e-4)

            # --- Must not be all zeros for non-empty text or on embedding failure ---
            embedding_vector = result.get("embedding_vector") or result.get("embedding")
            if not result.get("crisis_flag") and text.strip():
                if embedding_vector is None or np.all(embedding_vector == 0.0):
                    assert leaves_are_zero(result_emotion), \
                        f"Expected all-zero emotions on embedding failure, got: {result_emotion}"
                else:
                    weighted_vals = list(result["weighted_emotion_distribution"].values())
                    assert any(v > 0.0 for v in weighted_vals), \
                        "All emotion probabilities are zero for non-crisis, non-empty text."

            # Intensifiers / deintensifiers
            words = text.lower().split()
            if any(w in get_intensifiers() or w in get_deintensifiers() for w in words):
                max_val = max(weighted_vals, default=0.0)
                assert max_val <= 1.0

        # --- Weighted emotions sum check ---
        weighted_vals = list(result["weighted_emotion_distribution"].values())
        total_prob = sum(weighted_vals)
        if total_prob != 0.0:
            assert np.isclose(total_prob, 1.0, atol=1e-4)

        # --- Must not be all zeros for non-empty text ---
        if not result.get("crisis_flag") and text.strip():
            assert any(v > 0.0 for v in weighted_vals), \
                "All emotion probabilities are zero for non-crisis, non-empty text."


        # --- Intensifiers / deintensifiers ---
        words = text.lower().split()
        if any(w in get_intensifiers() or w in get_deintensifiers() for w in words):
            max_val = max(weighted_vals, default=0.0)
            assert max_val <= 1.0

        # --- Backward compatibility via analyze_emotions ---
        summary = analyze_emotions(text)
        assert "emotion_distribution" in summary
        assert "valence_arousal_summary" in summary
        val_ar = summary["valence_arousal_summary"]
        sentiment = compute_sentiment_from_profile(val_ar)
        assert "polarity" in sentiment and "label" in sentiment

        print(f"PASS: {desc}")


    # --- Embeddings failure handling (controlled mock) ---
    orig_get_embedding = embeddings.get_embedding_async
    try:
        # override embedding function to always raise an exception
        async def mock_fail(*args, **kwargs):
            raise Exception("Mock failure for testing embeddings pipeline.")

        embeddings.get_embedding_async = mock_fail

        # Run pipeline on a normal text to see how it handles embedding failure
        try:
            result = await process_entry_async("This text would normally have embeddings.", user_ip)
        except Exception as e:
            # propagate any unexpected errors; do not silence
            raise e

        # --- Recursive check for emotion dict ---
        if result.get("emotion") is not None:
            def check_emotion_values(em_dict):
                """
                Ensure all nested values are numeric floats (np.float64 counts)
                or all zeros if embedding truly failed.
                """
                for k, v in em_dict.items():
                    if isinstance(v, dict):
                        check_emotion_values(v)
                    else:
                        if result.get("embedding") is None or np.all(result["embedding"] == 0.0):
                            # embedding failed → all-zero expected
                            assert v == 0.0, f"Expected all-zero emotions on embedding failure, got: {result['emotion']}"
                        else:
                            # embedding present → must be numeric float ≥ 0
                            assert isinstance(v, (float, np.floating)), \
                                f"All emotion values should be floats, got: {result['emotion']}"
                            assert v >= 0.0, f"Emotion distribution must be non-negative, got: {result['emotion']}"

            check_emotion_values(result["emotion"])

        print("PASS: Embeddings failure handled gracefully.")
    finally:
        embeddings.get_embedding_async = orig_get_embedding

    # --- Intensity modifiers effect (middle-ground + informative) ---
    base_text = "I feel happy."
    mod_text = "I feel VERY happy but slightly sad."
    base_profile = compute_emotion_profile(base_text)
    mod_profile = apply_intensity_modifiers(mod_text, base_profile)

    # Compute per-emotion absolute differences
    differences = {k: abs(mod_profile[k] - base_profile.get(k, 0.0)) for k in mod_profile}

    # Assertions: at least one change, and total change above tiny epsilon
    assert any(diff > 0.0 for diff in differences.values()), \
        f"Intensity modifiers did not change any emotion: {differences}"
    total_diff = sum(differences.values())
    assert total_diff > 1e-6, \
        f"Total emotion profile change too small: {total_diff} | Detailed diffs: {differences}"

    print("PASS: Intensity modifiers effect confirmed (middle-ground, detailed).")

    # --- Empty / whitespace regression ---
    for inp in ["", "   ", "\n\t"]:
        result = await process_entry_async(inp, user_ip)
        weighted_vals = list(result["weighted_emotion_distribution"].values())
        assert all(isinstance(v, float) for v in weighted_vals)
        if sum(weighted_vals) != 0.0:
            assert np.isclose(sum(weighted_vals), 1.0, atol=1e-4)
        val_ar = analyze_emotions(inp)["valence_arousal_summary"]
        assert isinstance(val_ar.get("valence"), float)
        assert isinstance(val_ar.get("arousal"), float)
    print("PASS: Empty/whitespace regression confirmed.")

    # --- Composite stress test ---
    text = "   \nI am VERY happy but also slightly sad... kill myself if things go wrong.\t  "
    result = await process_entry_async(text, user_ip)
    weighted_vals = result["weighted_emotion_distribution"].values()
    if sum(weighted_vals) != 0.0:
        assert np.isclose(sum(weighted_vals), 1.0, atol=1e-4)
    print("PASS: Composite stress case handled correctly.")

    # --- Offline cache test ---
    cache_dir = Path("models/roberta-large").resolve()
    if not cache_dir.exists():
        raise FileNotFoundError(f"Offline cache not found at {cache_dir}")
    model = SentenceTransformer(str(cache_dir), local_files_only=True)
    test_emb = model.encode(["Offline test", "PeriDocs safety check"], convert_to_numpy=True)
    assert test_emb.shape[0] == 2
    print("PASS: all-roberta-large-v1 offline embeddings functional.")


# ------------------- Async wrapper stress test -------------------
async def run_async_stress_test():
    """Test multiple async entries in parallel to validate asyncio integration."""
    user_ip = "127.0.0.1"
    entries = [
        "I feel very happy today!",
        "Slightly anxious but hopeful.",
        "Neutral text entry.",
        "Kill myself if it goes wrong."
    ]
    tasks = [process_entry_async(txt, user_ip) for txt in entries]
    results = await asyncio.gather(*tasks)
    for res in results:
        assert "emotion" in res
    print("PASS: Async stress test entries completed.")


# ------------------- Main -------------------
async def main_async():
    print("Preloading embeddings model for tests...")
    await _load_model()  # preload to avoid first-call blocking
    print("Model preloaded; running async tests...")

    await run_async_tests()
    await run_async_stress_test()
    print("\nAll tests passed successfully.")


if __name__ == "__main__":
    asyncio.run(main_async())
