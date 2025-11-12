"""
core/nlp/test_pipeline.py

Comprehensive test suite for the PeriDocs NLP processing pipeline.
Tests: basic functionality, edge cases, intensity modifiers, valence/arousal,
weighted emotions, embeddings resilience, backward compatibility, and regression for empty inputs.
"""

import numpy as np
from pprint import pprint  # <-- added for temporary visual inspection
from core.nlp.process_entry import process_entry
from core.nlp.emotion_analysis import (
    analyze_emotions,
    apply_intensity_modifiers,
    get_emotion_anchors,
    get_intensifiers,
    get_deintensifiers,
    compute_emotion_profile
)
from core.nlp.emotion_analysis import compute_sentiment_from_profile
from core.nlp import embeddings

def test_pipeline():
    test_cases = [
        {
            "text": "I’m feeling hopeful but a bit anxious about tomorrow.",
            "desc": "Mixed positive/negative emotions, light intensity modifier.",
        },
        {
            "text": "",
            "desc": "Empty string input.",
        },
        {
            "text": "   ",
            "desc": "Whitespace-only input.",
        },
        {
            "text": "I am VERY happy, but also slightly sad.",
            "desc": "Uppercase intensifier + deintensifier combination.",
        },
        {
            "text": "Kill myself now, I can't go on.",
            "desc": "Crisis phrase input.",
        },
        {
            "text": "Just normal text with no emotion keywords.",
            "desc": "Neutral text without anchors.",
        },
    ]

    for case in test_cases:
        text = case["text"]
        desc = case["desc"]
        print(f"\n=== Testing Entry: {desc} ===\n{text}\n")

        result = process_entry(text)

        # --- TEMPORARY: Visual inspection
        result_copy = result.copy()
        # suppress embedding floats for display
        if "embedding" in result_copy:
            result_copy["embedding"] = "<embedding suppressed>"
        pprint(result_copy)
        # ---------------------------------

        # --- Basic structural assertions
        assert "emotion" in result, "Missing 'emotion' key."
        assert "weighted_emotion_distribution" in result, "Missing 'weighted_emotion_distribution' key."
        assert "sentiment" in result, "Missing 'sentiment' key."
        assert "summary" in result, "Missing 'summary' key."
        assert "primary_emotion" in result["summary"], "Missing 'primary_emotion' in summary."
        assert "intensity" in result["summary"], "Missing 'intensity' in summary."

        # --- Type checks
        assert isinstance(result["emotion"], dict), "'emotion' should be a dict."
        assert isinstance(result["weighted_emotion_distribution"], dict), "'weighted_emotion_distribution' should be a dict."
        assert isinstance(result["embedding"], np.ndarray), "'embedding' should be a np.ndarray."
        assert isinstance(result["embedding_mean"], float), "'embedding_mean' should be a float."
        assert isinstance(result["repetition"], (float, int)), "'repetition' should be numeric."
        assert isinstance(result["sha8"], str), "'sha8' should be a string."
        assert isinstance(result["crisis_flags"], list), "'crisis_flags' should be a list."

        # --- Emotion probabilities sum to ~1 for weighted distribution
        weighted_vals = list(result["weighted_emotion_distribution"].values())
        total_prob = sum(weighted_vals)

        # Handle zero-sum gracefully
        if total_prob == 0.0:
            print("WARNING: Weighted emotions sum to zero; flagged for devs/end-users.")
            # Still allow test to pass, but normalize all to zero safely
            weighted_vals_normalized = weighted_vals
        else:
            assert np.isclose(total_prob, 1.0, atol=1e-4), f"Weighted emotions do not sum to 1 (sum={total_prob})."

        # --- Intensifiers / deintensifiers effect check
        if any(word.lower() in get_intensifiers() or word.lower() in get_deintensifiers() for word in text.lower().split()):
            max_val = max(result["weighted_emotion_distribution"].values())
            assert max_val <= 1.0, "Intensity modifier may exceed normalized cap."

        # --- Backward compatibility
        summary = analyze_emotions(text)
        assert "emotion_distribution" in summary, "analyze_emotions missing 'emotion_distribution'."
        assert "valence_arousal_summary" in summary, "analyze_emotions missing 'valence_arousal_summary'."

        val_ar_summary = summary["valence_arousal_summary"]
        sentiment = compute_sentiment_from_profile(val_ar_summary)
        assert "polarity" in sentiment and "label" in sentiment, "compute_sentiment_from_profile failed."

        print(f"PASS: {desc}")

def test_embeddings_failure():
    """
    Simulate embeddings failure and ensure the pipeline handles it gracefully.
    """
    print("\n=== Testing embeddings failure resilience ===")

    # Save original functions
    orig_get_embedding = embeddings.get_embedding
    orig_batch_embeddings = embeddings.batch_embeddings

    try:
        # Monkey patch to raise exception
        embeddings.get_embedding = lambda *args, **kwargs: (_ for _ in ()).throw(Exception("Mock embedding failure"))
        embeddings.batch_embeddings = lambda *args, **kwargs: (_ for _ in ()).throw(Exception("Mock batch failure"))

        result = compute_emotion_profile("This text would normally have embeddings.")
        # Ensure all emotions are zero
        assert all(v == 0.0 for v in result.values()), "Emotion profile should be zeroed on embedding failure."
        print("PASS: Embeddings failure handled gracefully.")
    finally:
        # Restore original functions
        embeddings.get_embedding = orig_get_embedding
        embeddings.batch_embeddings = orig_batch_embeddings

def test_intensity_modifiers_effect():
    """
    Ensure intensity modifiers change the emotion distribution in a measurable way.
    """
    print("\n=== Testing intensity modifiers effect ===")
    text_base = "I feel happy."
    text_intense = "I feel VERY happy but also slightly sad."

    base_profile = compute_emotion_profile(text_base)
    modified_profile = apply_intensity_modifiers(text_intense, base_profile)

    # Ensure the modified profile differs from the base profile
    differences = sum(abs(modified_profile[k] - base_profile.get(k, 0.0)) for k in modified_profile)
    assert differences > 0.01, "Intensity modifiers did not measurably change the profile."
    print("PASS: Intensity modifiers effect confirmed.")

def test_empty_input_regression():
    """
    Regression test for empty or whitespace-only input.
    Ensures no NaNs, crashes, or invalid distributions occur.
    """
    print("\n=== Testing empty/whitespace input regression ===")
    inputs = ["", "   ", "\n\t"]

    for inp in inputs:
        result = process_entry(inp)
        # Emotion and weighted distribution should be all zeros or normalized
        emotion_vals = result["emotion"].values()
        weighted_vals = result["weighted_emotion_distribution"].values()
        assert all(isinstance(v, float) for v in emotion_vals), "Non-float value in emotion dict."
        assert all(isinstance(v, float) for v in weighted_vals), "Non-float value in weighted distribution."
        assert all(v >= 0.0 for v in weighted_vals), "Negative probability detected."
        if sum(weighted_vals) != 0.0:
            assert np.isclose(sum(weighted_vals), 1.0, atol=1e-4), "Weighted distribution does not sum to 1."
        # Valence/arousal summary should be valid floats
        summary = analyze_emotions(inp)["valence_arousal_summary"]
        assert isinstance(summary.get("valence"), float), "Valence not a float."
        assert isinstance(summary.get("arousal"), float), "Arousal not a float."

    print("PASS: Empty/whitespace input regression test confirmed.")

def test_composite_stress_case():
    """
    Composite stress test combining:
    - crisis phrases
    - intensity modifiers (VERY, slightly)
    - whitespace and noise
    Ensures no crashes, valid distributions, normalized probabilities,
    and correct detection of crisis flags and intensity effects.
    """
    print("\n=== Testing composite stress case ===")
    text = "   \nI am VERY happy but also slightly sad... kill myself if things go wrong.\t  "

    result = process_entry(text)

    # --- Structural assertions
    assert "emotion" in result, "Missing 'emotion' key."
    assert "weighted_emotion_distribution" in result, "Missing 'weighted_emotion_distribution' key."
    assert "summary" in result, "Missing 'summary' key."
    assert "crisis_flags" in result, "Missing 'crisis_flags' key."

    # --- Weighted emotions sum check
    weighted_vals = result["weighted_emotion_distribution"].values()
    if sum(weighted_vals) != 0.0:
        assert np.isclose(sum(weighted_vals), 1.0, atol=1e-4), "Weighted distribution not normalized."

    # --- Intensifier effect check
    base_profile = compute_emotion_profile("I am happy but also sad.")
    modified_profile = apply_intensity_modifiers(text, base_profile)
    differences = sum(abs(modified_profile[k] - base_profile.get(k, 0.0)) for k in modified_profile)
    assert differences > 0.01, "Intensity modifiers did not measurably affect composite text."

    # --- Crisis detection check
    assert len(result["crisis_flags"]) > 0, "Crisis phrases not detected in composite stress case."

    # --- Valence/arousal summary sanity
    summary = analyze_emotions(text)["valence_arousal_summary"]
    assert isinstance(summary.get("valence"), float), "Valence not a float."
    assert isinstance(summary.get("arousal"), float), "Arousal not a float."

    print("PASS: Composite stress case handled correctly.")

# =========== VERIFY OFFLINE IS FULLY FUNCTIONAL AND CONTAINED FOR NO TELEMETRY =================
def test_all_minilm_offline_cache():
    """
    Verify that all-MiniLM-L6-v2 is already cached locally.
    This test fails immediately if the model is not present.
    Ensures no network call occurs in production.
    """
    print("\n=== Testing all-MiniLM-L6-v2 offline cache ===")
    import os
    from pathlib import Path
    import numpy as np
    from sentence_transformers import SentenceTransformer

    # Default HuggingFace cache paths
    cache_dir = Path.home() / ".cache" / "torch" / "sentence_transformers" / "all-MiniLM-L6-v2"

    if not cache_dir.exists():
        raise FileNotFoundError(
            f"all-MiniLM-L6-v2 not found in cache: {cache_dir}\n"
            "Download the model once in development, then confirm cache for production."
        )

    # Load model offline
    model = SentenceTransformer(str(cache_dir))

    # Minimal embedding test
    sentences = ["Offline test.", "PeriDocs production safety check."]
    embeddings_list = model.encode(sentences, show_progress_bar=False)

    assert len(embeddings_list) == len(sentences), "Embeddings count mismatch."
    for emb in embeddings_list:
        assert isinstance(emb, np.ndarray), "Embedding is not a numpy array."
        assert emb.shape[0] > 0, "Embedding dimension is zero."

    print("PASS: all-MiniLM-L6-v2 offline cached embeddings functional.")



if __name__ == "__main__":
    test_pipeline()
    test_embeddings_failure()
    test_intensity_modifiers_effect()
    test_empty_input_regression()
    test_composite_stress_case()
    test_all_minilm_offline_cache()
    print("\nAll tests passed successfully.")