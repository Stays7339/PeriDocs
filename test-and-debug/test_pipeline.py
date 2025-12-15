# ==========================================
# core/nlp/test_pipeline.py
# save-state updated 202512151512
# ==========================================
import os
from pathlib import Path
import asyncio
import json
from datetime import datetime
import numpy as np
from dotenv import load_dotenv

from core.nlp.process_entry import process_entry_async
from core.nlp.embeddings import _load_model
from core.nlp.encryption import decrypt_text

# ================== CONFIGURATION ==================
# Crisis bypass exists
SKIP_CRISIS_CHECK = False

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

if not ENV_PATH.exists():
    raise FileNotFoundError(f".env file not found at {ENV_PATH}")

load_dotenv(ENV_PATH)
AES_KEY = os.environ.get("PERIDOCS_AES_KEY")
if not AES_KEY or AES_KEY.strip() == "":
    raise ValueError(".env missing PERIDOCS_AES_KEY")

# ================== UTILITY ==================
def get_local_ip() -> str:
    return "127.0.0.1"

# ================== CORE ASYNC TESTS ==================
async def run_async_tests():
    user_ip = get_local_ip()

    test_cases = [
        ("I’m feeling hopeful but a bit anxious about tomorrow.",
         "Mixed positive/negative emotions"),
        ("Just normal text with no emotion keywords.",
         "Neutral text"),
    ]

    for text, desc in test_cases:
        print(f"\n=== Testing Entry: {desc} ===")
        result = await process_entry_async(text, user_ip)

        # Embedding checks
        embedding = result.get("embedding")
        assert isinstance(embedding, list)
        assert len(embedding) == 1024

        # Emotion checks
        assert result.get("dominant_emotion") is not None
        emotions = result.get("emotions")
        assert isinstance(emotions, dict)
        for v in emotions.values():
            assert 0.0 <= v <= 1.0

        # Timestamp validity
        datetime.fromisoformat(result["timestamp_utc"])

        print(f"PASS: {desc}")

# ================== EMPTY / WHITESPACE ==================
async def run_empty_input_tests():
    ip = get_local_ip()

    try:
        await process_entry_async("", ip)
        raise AssertionError("Empty string was not rejected")
    except ValueError:
        pass

    try:
        await process_entry_async("   \n\t   ", ip)
        raise AssertionError("Whitespace string was not rejected")
    except ValueError:
        pass

    print("PASS: Empty & whitespace rejection")

# ================== CRISIS PATH ==================
"""Crisis entries omit emotion fields by design to prevent inference during safety handling."""


async def run_crisis_test():
    ip = get_local_ip()
    text = "I want to kill myself."

    result = await process_entry_async(text, ip)

    assert result["crisis_flag"] is True
    assert result["embedding"] is None
    assert "dominant_emotion" not in result
    assert "emotions" not in result
    assert result["crisis_warning"] is not None

    print("PASS: Crisis-path behavior")

# ================== PII REDACTION ==================
async def run_pii_test():
    ip = get_local_ip()
    text = "My name is John Smith and my email is john@example.com"

    result = await process_entry_async(text, ip)

    assert result["safe_text"] != text
    assert "@" not in result["safe_text"]

    print("PASS: PII redaction")

# ================== HASH REPRODUCIBILITY ==================
async def run_hash_test():
    ip = get_local_ip()
    text = "Consistent hashing test."

    r1 = await process_entry_async(text, ip)
    r2 = await process_entry_async(text, ip)

    assert r1["sha8"] == r2["sha8"]
    assert r1["pseudonym_hash"] == r2["pseudonym_hash"]

    print("PASS: Hash reproducibility")

# ================== ENCRYPTION ROUND-TRIP ==================
async def run_encryption_test():
    ip = get_local_ip()
    text = "Encryption round-trip test."

    result = await process_entry_async(text, ip)
    decrypted = decrypt_text(result["encrypted_text"])

    assert decrypted == result["safe_text"]

    print("PASS: Encryption round-trip")
# ================== JSON PERSISTENCE ==================
async def run_json_persistence_test():
    """
    Validate that NLP output can be safely serialized and deserialized
    using the application's JSON persistence rules.
    """
    from app.helpers.file_ops import save_data, load_data

    ip = get_local_ip()
    text = "JSON persistence test."

    result = await process_entry_async(text, ip)
    path = PROJECT_ROOT / "tmp_test_entry.json"

    # Write via app helper (normalization happens here)
    save_data([result], file_path=str(path))

    # Read back via same helper
    loaded = load_data(file_path=str(path))
    assert len(loaded) == 1

    loaded_entry = loaded[0]

    assert loaded_entry["sha8"] == result["sha8"]
    assert loaded_entry["encrypted_text"] == result["encrypted_text"]

    path.unlink(missing_ok=True)

    print("PASS: JSON read/write persistence")


# ================== ASYNC STRESS TEST ==================
async def run_async_stress_test():
    ip = get_local_ip()
    entries = [
        "I feel very happy today!",
        "Slightly anxious but hopeful.",
        "Neutral text entry.",
    ]

    results = await asyncio.gather(
        *[process_entry_async(t, ip) for t in entries]
    )

    for res in results:
        assert res.get("dominant_emotion") is not None

    print("PASS: Async stress test")

# ================== MAIN ==================
async def main_async():
    print("Preloading embeddings model for tests...")
    await _load_model()
    print("Model preloaded.\n")

    await run_async_tests()
    await run_empty_input_tests()
    await run_crisis_test()
    await run_pii_test()
    await run_hash_test()
    await run_encryption_test()
    await run_json_persistence_test()
    await run_async_stress_test()

    print("\nAll tests passed successfully.")

# ================== ENTRY ==================
if __name__ == "__main__":
    asyncio.run(main_async())
