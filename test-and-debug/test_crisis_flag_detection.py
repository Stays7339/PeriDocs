# ==========================================
# test_crisis_flag_detection.py
# Save-state: 202512201932
# ==========================================
from core.nlp.process_entry import process_entry_async
from core.nlp.crisis_detector import (
    check_crisis_phrases_async,
    get_crisis_phrases
)
import asyncio

# ---------------- CONFIG ----------------
DEBUG_MATCHES = True

# ---------------- Live crisis phrases ----------------
CRISIS_PHRASES = get_crisis_phrases()

# ---------------- Safe text examples ----------------
SAFE_TEXTS = [
    "I feel a bit sad today but I will be fine.",
    "Looking forward to my trip next week!",
    "Work was stressful, but I handled it well.",
    "I had some anxiety, but nothing extreme.",
    "This is just normal diary text, nothing dangerous here."
]

# ---------------- Typo / filler / gap variants ----------------
FUZZY_TESTS = [
    "I feel like I want die today.",
    "Sometimes I will end, my life...",
    "Can't go on???",
    "tired ... of living",
    "wish I wre dead",
    "end it all !!"
]

# ---------------- Multi-word / punctuation / filler tests ----------------
MULTIWORD_GAP_TESTS = [
    "Sometimes I feel like I want... to die today.",
    "I can't, go on, anymore.",
    "End; my; life now!",
    "I am tired, of, living",
    "Wish I were - dead",
    "Suicide? Never thought about it seriously.",
    "I wish I, were, dead.",
    "Kill myself? No, just a thought."
]

# ---------------- Implicit intent tests ----------------
IMPLICIT_INTENT_TESTS = [
    "I am thinking about die.",
    "I might die tomorrow.",
    "Planning to die soon.",
    "I keep thinking about being dead."
]


# ---------------- Result cache ----------------
_RESULT_CACHE = {}

async def run_cached(text: str, user_ip: str):
    """
    Ensures each entry is processed once per test run.
    Prevents repeated model loads / duplicate async work.
    """
    if text not in _RESULT_CACHE:
        _RESULT_CACHE[text] = await process_entry_async(text, user_ip)
    return _RESULT_CACHE[text]

# ---------------- Debug function ----------------
async def debug_flagged_entries(entries):
    if not DEBUG_MATCHES:
        return

    print("\n=== DEBUG: FLAGGED ENTRY DETAILS ===")
    for text in entries:
        result = await run_cached(text, "127.0.0.1")
        if result.get("crisis_flag"):
            matches = await check_crisis_phrases_async(text)
            print(f"\nEntry: '{text}'")
            print(f"Matched Crisis Phrases: {matches}")

# ---------------- Multi-word test runner ----------------
async def run_multiword_gap_tests(user_ip):
    failed = False
    print("\n=== MULTI-WORD / PUNCTUATION / FILLER TESTS ===")

    for text in MULTIWORD_GAP_TESTS:
        result = await run_cached(text, user_ip)
        if result.get("crisis_flag"):
            print(f"✅ Correctly flagged: '{text}'")
        else:
            print(f"❌ Missed flag: '{text}'")
            failed = True

    if not failed:
        print("🎯 All multi-word tests passed.")
    else:
        print("⚠ Some multi-word tests failed.")

    await debug_flagged_entries(MULTIWORD_GAP_TESTS)

# ---------------- Implicit intent test runner ----------------
async def run_implicit_intent_tests(user_ip):
    failed = False
    print("\n=== IMPLICIT INTENT TESTS ===")

    for text in IMPLICIT_INTENT_TESTS:
        result = await run_cached(text, user_ip)
        if result.get("crisis_flag"):
            print(f"✅ Correctly flagged implicit: '{text}'")
        else:
            print(f"❌ Missed implicit intent: '{text}'")
            failed = True

    await debug_flagged_entries(IMPLICIT_INTENT_TESTS)

    if not failed:
        print("🎯 All implicit intent tests passed.")
    else:
        print("⚠ Some implicit intent tests failed.")

# ---------------- Main runner ----------------
async def run_tests():
    user_ip = "127.0.0.1"
    failed = False

    print("=== CRISIS PHRASE TEST ===")
    for phrase in CRISIS_PHRASES:
        text = f"Sometimes I feel like {phrase}."
        result = await run_cached(text, user_ip)
        if result.get("crisis_flag"):
            print(f"✅ Flagged: '{text}'")
        else:
            print(f"❌ Not flagged: '{text}'")
            failed = True

    print("\n=== FUZZY / TYPO TESTS ===")
    for text in FUZZY_TESTS:
        result = await run_cached(text, user_ip)
        if result.get("crisis_flag"):
            print(f"✅ Flagged fuzzy: '{text}'")
        else:
            print(f"❌ Missed fuzzy: '{text}'")
            failed = True

    print("\n=== SAFE TEXT TEST ===")
    for text in SAFE_TEXTS:
        result = await run_cached(text, user_ip)
        if result.get("crisis_flag"):
            print(f"❌ False positive: '{text}'")
            failed = True
        else:
            print(f"✅ Safe: '{text}'")

    await debug_flagged_entries(
        CRISIS_PHRASES + FUZZY_TESTS + SAFE_TEXTS
    )

    await run_multiword_gap_tests(user_ip)

    if not failed:
        print("\n🎯 ALL TESTS PASSED")
    else:
        print("\n⚠ TEST FAILURES DETECTED")

    await run_implicit_intent_tests(user_ip)


if __name__ == "__main__":
    asyncio.run(run_tests())

