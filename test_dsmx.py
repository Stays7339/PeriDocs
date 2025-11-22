import numpy as np
from core.nlp.emotion_analysis import compute_emotion_profile, get_emotion_anchors

def test_dsmx_deterministic_behavior():
    """
    Ensures that the DSMX (deterministic softmax) transformation produces
    stable, repeatable results and retains valid probability semantics.
    """

    text = "The situation is extremely confusing but I feel a bit hopeful."

    # Run the profile multiple times within the same interpreter
    try:
        dist1 = compute_emotion_profile(text)
        dist2 = compute_emotion_profile(text)
        dist3 = compute_emotion_profile(text)
    except Exception as e:
        raise RuntimeError(f"Embedding computation failed: {e}")

    # 1. All runs must be exactly identical (byte-level identical floats)
    for e in dist1:
        assert dist1[e] == dist2[e], f"Mismatch for '{e}': {dist1[e]} != {dist2[e]}"
        assert dist1[e] == dist3[e], f"Mismatch for '{e}': {dist1[e]} != {dist3[e]}"

    # 2. Probabilities must sum to ~1.0
    total = sum(dist1.values())
    assert np.isclose(total, 1.0, atol=1e-7), f"sum={total}"

    # 3. No negative or NaN values
    for p in dist1.values():
        assert p >= 0.0, f"Negative probability detected: {p}"
        assert not np.isnan(p), "NaN probability detected"

    # 4. Deterministic tie-breaking:
    #    When providing symmetrically emotion-neutral input,
    #    ordering must be stable across runs.
    neutral_text = "word"
    try:
        dA = compute_emotion_profile(neutral_text)
        dB = compute_emotion_profile(neutral_text)
    except Exception as e:
        raise RuntimeError(f"Embedding computation failed for neutral text: {e}")

    # All emotions should preserve consistent ordering
    ordering_A = list(sorted(dA.items(), key=lambda x: x[1], reverse=True))
    ordering_B = list(sorted(dB.items(), key=lambda x: x[1], reverse=True))
    assert ordering_A == ordering_B, "Non-deterministic ordering detected"

if __name__ == "__main__":
    print("Running DSMX deterministic tests...")
    test_dsmx_deterministic_behavior()
    print("DSMX tests passed.")
    print("Emotion anchors:", get_emotion_anchors())
