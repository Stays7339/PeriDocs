# ==========================================
# test_crisis_flag_safety.py
# ==========================================

from core.nlp.process_entry import process_entry_async
import asyncio

# ---------------- Test Texts ----------------
safe_texts = [
    "I feel a bit sad today but I will be fine.",
    "Looking forward to my trip next week!",
    "Work was stressful, but I handled it well.",
    "I had some anxiety, but nothing extreme.",
    "This is just normal diary text, nothing dangerous here."
]

async def test_no_false_crisis_flags():
    user_ip = "127.0.0.1"
    failed = False

    for text in safe_texts:
        result = await process_entry_async(text, user_ip)
        if result.get("crisis_flag"):
            print("❌ False positive detected for text:", text)
            failed = True
        else:
            print("✅ Correctly not flagged:", text)

    if not failed:
        print("\nAll safe texts correctly avoided crisis flag.")

if __name__ == "__main__":
    asyncio.run(test_no_false_crisis_flags())
