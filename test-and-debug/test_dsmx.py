import numpy as np
from core.nlp.emotion_analysis import compute_emotion_profile_async, get_emotion_anchors

import numpy as np
import asyncio
from core.nlp.emotion_analysis import compute_emotion_profile_async, get_emotion_anchors

async def test_dsmx_deterministic_behavior():
    text = "The situation is extremely confusing but I feel a bit hopeful."

    dist1 = await compute_emotion_profile_async(text)
    dist2 = await compute_emotion_profile_async(text)
    dist3 = await compute_emotion_profile_async(text)

    print("=== Emotion distributions for repeated runs ===")
    print("dist1:", dist1)
    print("dist2:", dist2)
    print("dist3:", dist3)

    # Same assertions as before
    for e in dist1:
        assert np.isclose(dist1[e], dist2[e], atol=1e-10)
        assert np.isclose(dist1[e], dist3[e], atol=1e-10)

    total = sum(dist1.values())
    print(f"Sum of probabilities: {total}")
    assert np.isclose(total, 1.0, atol=1e-7)

    anchors = get_emotion_anchors()
    missing = [e for e in anchors if e not in dist1]
    print("Missing emotions (should be empty):", missing)
    assert not missing

# Run the async test from sync context
if __name__ == "__main__":
    print("Running DSMX deterministic tests...")
    asyncio.run(test_dsmx_deterministic_behavior())
    print("DSMX tests passed.")
    print("Emotion anchors:", get_emotion_anchors())
