# ==========================================
# test_crisis_flag_detection.py
# ==========================================

from core.nlp.process_entry import process_entry_async
from core.nlp.anchors import get_crisis_phrases
import asyncio

async def test_crisis_phrases_trigger_flag():
    user_ip = "127.0.0.1"
    failed = False

    for phrase in get_crisis_phrases():
        # Wrap phrase in a sentence to simulate normal usage
        text = f"Sometimes I feel like {phrase}."
        result = await process_entry_async(text, user_ip)
        if not result.get("crisis_flag"):
            print("❌ Failed to flag crisis phrase:", phrase)
            failed = True
        else:
            print("✅ Correctly flagged:", phrase)

    if not failed:
        print("\nAll crisis phrases correctly triggered crisis_flag.")

if __name__ == "__main__":
    asyncio.run(test_crisis_phrases_trigger_flag())
