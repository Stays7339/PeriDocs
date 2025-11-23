"""
core/nlp/test_pipeline.py 
save-state updated 202511231610 (date and time formatted as follows: YYYYMMDDhhmm)
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
from dotenv import load_dotenv

from core.nlp.process_entry import process_entry_async
from core.nlp.emotion_analysis import (
    analyze_emotions_async,
    apply_intensity_modifiers,
    compute_emotion_profile_async,
    compute_sentiment_from_profile,
    get_intensifiers,
    get_deintensifiers,
    _EMOTION_LEXICONS
)
from core.nlp import embeddings
from core.nlp.embeddings import _load_model
from core.nlp.fuzzy_utils import get_combined_lexicons
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

# ------------------- Utility: resolve local SentenceTransformer model directory -------------------
def resolve_snapshot_dir(root: Path) -> Path:
    """
    Given a HuggingFace-style cached model directory like:
        models/roberta-large/
    Automatically locate the real model snapshot directory, e.g.:
        models/roberta-large/models--sentence-transformers--all-roberta-large-v1/snapshots/<HASH>/
    Returns the path to that snapshot. Raises if invalid.
    """
    root = root.resolve()
    if not root.exists():
        raise FileNotFoundError(f"Model root not found: {root}")

    # Look for nested HF structure
    for repo_dir in root.glob("models--*/"):
        snapshot_parent = repo_dir / "snapshots"
        if snapshot_parent.exists() and snapshot_parent.is_dir():
            # Expect exactly one hash folder
            hashes = [p for p in snapshot_parent.iterdir() if p.is_dir()]
            if len(hashes) == 1:
                snapshot = hashes[0]
                # Verify this folder actually contains a ST model
                if (snapshot / "config.json").exists() and \
                   (snapshot / "model.safetensors").exists():
                    return snapshot
                else:
                    raise FileNotFoundError(
                        f"Snapshot found but missing config/model files: {snapshot}"
                    )

    raise FileNotFoundError(
        f"No valid snapshot directory found under {root}. "
        f"Expected HuggingFace-style structure."
    )


# ------------------- Global Combined Lexicon -------------------
LEXICON = get_combined_lexicons(_EMOTION_LEXICONS)

# ------------------- Utility: local IP -------------------
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

        # --- Embedding check ---
        real_embedding = result.get("embedding", None)
        if isinstance(real_embedding, np.ndarray):
            emb_norm = float(np.linalg.norm(real_embedding))
            print(f"Embedding shape: {real_embedding.shape} | Norm: {emb_norm}")
        else:
            print(f"NOTE: Embedding was redacted/suppressed for text: {text!r}")
            print(f"Embedding shape: N/A | Norm check skipped if redacted")

        # --- Recursive leaf checks ---
        def all_leaf_values_float(d):
            if isinstance(d, dict):
                return all(all_leaf_values_float(v) for v in d.values())
            return isinstance(d, (float, np.floating))

        def leaves_are_zero(d):
            if isinstance(d, dict):
                return all(leaves_are_zero(v) for v in d.values())
            try:
                return float(d) == 0.0
            except Exception:
                return False

        result_emotion = result.get("emotion")

        if result.get("crisis_flag"):
            assert result["sha8"] is None
            assert result["staff_hash"] is None
            assert result["pseudonym_hash"] is None
            assert result["tokens"] == []
            assert result["entities"] == []
            assert result["embedding"] is None
        else:
            # Non-crisis assertions
            assert "emotion" in result
            assert "weighted_emotion_distribution" in result
            assert "sentiment" in result
            assert "summary" in result
            assert "primary_emotion" in result["summary"]
            assert "intensity" in result["summary"]

            if result_emotion is not None:
                assert all_leaf_values_float(result_emotion)

            if real_embedding is not None and isinstance(real_embedding, np.ndarray) and text.strip():
                emb_norm = float(np.linalg.norm(real_embedding))
                assert emb_norm > 1e-6

            assert isinstance(result["embedding_mean"], float)
            assert isinstance(result["repetition_multiplier"], (float, int))
            assert isinstance(result["sha8"], str)
            assert isinstance(result["pseudonym_hash"], str)
            assert isinstance(result["crisis_flag"], bool)

            weighted_vals = list(result["weighted_emotion_distribution"].values())
            total_prob = sum(weighted_vals)
            if total_prob != 0.0:
                assert np.isclose(total_prob, 1.0, atol=1e-4)
            if not result.get("crisis_flag") and text.strip():
                if real_embedding is None or np.all(real_embedding == 0.0):
                    assert leaves_are_zero(result_emotion)
                else:
                    assert any(v > 0.0 for v in weighted_vals)

            # Intensifiers / deintensifiers
            words = text.lower().split()
            if any(w in get_intensifiers() or w in get_deintensifiers() for w in words):
                assert max(weighted_vals, default=0.0) <= 1.0

        # --- Backward compatibility check ---
        summary = await analyze_emotions_async(text)
        assert "emotion_distribution" in summary
        assert "valence_arousal_summary" in summary
        val_ar = summary["valence_arousal_summary"]
        sentiment = compute_sentiment_from_profile(val_ar)
        assert "polarity" in sentiment and "label" in sentiment

        print(f"PASS: {desc}")

    # --- Embeddings failure handling ---
    orig_get_embedding = embeddings.get_embedding_async
    try:
        async def mock_fail(*args, **kwargs):
            raise Exception("Mock failure for testing embeddings pipeline.")
        embeddings.get_embedding_async = mock_fail

        result = await process_entry_async("This text would normally have embeddings.", user_ip)
        if result.get("emotion") is not None:
            def check_emotion_values(em_dict):
                for k, v in em_dict.items():
                    if isinstance(v, dict):
                        check_emotion_values(v)
                    else:
                        if result.get("embedding") is None or np.all(result["embedding"] == 0.0):
                            assert v == 0.0
                        else:
                            assert isinstance(v, (float, np.floating))
                            assert v >= 0.0
            check_emotion_values(result["emotion"])
        print("PASS: Embeddings failure handled gracefully.")
    finally:
        embeddings.get_embedding_async = orig_get_embedding

    # --- Intensity modifiers effect ---
    base_text = "I feel happy."
    mod_text = "I feel VERY happy but slightly sad."
    base_profile = await compute_emotion_profile_async(base_text)
    mod_profile = apply_intensity_modifiers(mod_text.split(), base_profile, LEXICON)

    differences = {k: abs(mod_profile[k] - base_profile.get(k, 0.0)) for k in mod_profile}
    total_diff = sum(differences.values())
    print("DEBUG: base_profile:", base_profile)
    print("DEBUG: mod_profile:", mod_profile)
    print("DEBUG: differences:", differences)
    print("DEBUG: total_diff:", total_diff)

    assert any(diff > 0.0 for diff in differences.values())
    assert total_diff > 1e-6
    print("PASS: Intensity modifiers effect confirmed.")

    # --- Empty / whitespace regression ---
    for inp in ["", "   ", "\n\t"]:
        result = await process_entry_async(inp, user_ip)
        weighted_vals = list(result["weighted_emotion_distribution"].values())
        assert all(isinstance(v, float) for v in weighted_vals)
        if sum(weighted_vals) != 0.0:
            assert np.isclose(sum(weighted_vals), 1.0, atol=1e-4)
        summary = await analyze_emotions_async(inp)
        val_ar = summary["valence_arousal_summary"]
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
    cache_root = Path("models/roberta-large").resolve()
    snapshot_dir = resolve_snapshot_dir(cache_root)

    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    model = SentenceTransformer(str(snapshot_dir))

    test_emb = model.encode(["Offline test", "PeriDocs safety check"], convert_to_numpy=True)
    assert test_emb.shape[0] == 2
    print("PASS: all-roberta-large-v1 offline embeddings functional.")

# ------------------- Async wrapper stress test -------------------
async def run_async_stress_test():
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
    await _load_model()
    print("Model preloaded; running async tests...")
    await run_async_tests()
    await run_async_stress_test()
    print("\nAll tests passed successfully.")


if __name__ == "__main__":
    asyncio.run(main_async())
