Perfect — here’s a **compact ASCII-style flow diagram** for the refactored `embeddings.py`, showing both **sync and async paths** and how caching, batching, and model preload interact. It can be pasted at the top of the file or kept in documentation.

```
          ┌───────────────────────────┐
          │       Raw Text Input      │
          └─────────────┬────────────┘
                        │
                        ▼
           ┌─────────────────────────┐
           │   get_embedding_async   │
           │ (single text entry)     │
           └─────────┬──────────────┘
                     │
   ┌─────────────────┴─────────────────┐
   │ Check _embedding_cache            │
   │ If cached → return immediately    │
   └─────────────────┬─────────────────┘
                     ▼
       ┌──────────────────────────┐
       │ batch_embeddings_async   │
       │ (single-item batch)      │
       └─────────┬────────────────┘
                 │
    ┌────────────┴─────────────┐
    │ Preload model if needed  │
    │ (_load_model async)      │
    └────────────┬─────────────┘
                 ▼
    ┌───────────────────────────────┐
    │ Split texts into executor     │
    │ batches (batch_size default 8)│
    └────────────┬──────────────────┘
                 ▼
       ┌───────────────────────┐
       │ _embed_sync (Thread)  │
       │ SentenceTransformer   │
       └─────────┬─────────────┘
                 ▼
       ┌───────────────────────┐
       │ Cache embeddings       │
       │ (_embedding_cache)     │
       └─────────┬─────────────┘
                 ▼
       ┌───────────────────────┐
       │ Return embedding(s)   │
       └───────────────────────┘
                 ▲
                 │
       ┌─────────┴─────────────┐
       │ get_embedding (sync)  │
       │ wrapper handles:      │
       │ - running loop check  │
       │ - asyncio scheduling  │
       │ - zero vector for ""  │
       └───────────────────────┘
```

### Notes / Reading the Diagram

1. **Single vs batch embeddings**:

   * `get_embedding_async` always leverages `batch_embeddings_async` internally for consistent caching.
   * `batch_embeddings_async` handles multiple texts in efficient executor batches.

2. **Caching**: `_embedding_cache` ensures repeated text embeddings are returned immediately without recomputation.

3. **Model preload**: `_load_model()` ensures both sync and async paths detect the nested model folder and load the model only once.

4. **Sync wrapper**: `get_embedding()` safely calls the async path, handling both running loop contexts and top-level execution.

5. **Zero vectors**: Both sync and async return zeros for empty or whitespace-only text to avoid null errors downstream.

---

 also **draft a mini “vertical module map” for the embeddings pipeline** that connects this file directly to `process_entry.py` and `emotion_analysis.py`—kind of like a zoomed-in PeriDocs NLP pipeline diagram. It makes onboarding and testing much easier.

 Here’s a **focused “zoomed-in” PeriDocs NLP embeddings pipeline map**, showing exactly how `embeddings.py` interacts with `process_entry.py` and `emotion_analysis.py`. This is meant to complement your full ASCII map but isolates the embedding flow for clarity.

## Fully corrected vertical-flow ASCII map as of 13 November 2025.

```
Raw Text Input
    │
    ▼
process_entry.py
    * text_processing.py.clean_text
    * text_processing.py.tokenize_text
    * pii.py.redact_pii
    * repetition_echo.py.weight_repetition
    * sentiment_analysis.py.analyze_sentiment
    * crisis.py.detect_crisis
    │
    ▼
text_processing.py.process_text
    │→ cleaned text
    │→ token_dicts
    │→ token_strings
    │→ features
    * text_processing.py.document_features
        │
        * _lexicon_emotion_features(tokens)
            │
            * detect_emotion_tokens(tokens)
                │
                * anchors.py._EMOTION_LEXICONS
                * fuzzy_utils.py.get_combined_lexicons
                * fuzzy_utils.py.fuzzy_matches_above
        │ outputs: 
            token_count
            emotion_anchor_hits
            raw_emotion_hits
        │
        * emotion_analysis.py.analyze_emotions(raw_text)
            │
            * embeddings.py.compute_embedding_vectors
            │ outputs:
                embedding_emotion_distribution
                valence_arousal_summary
    │
    ▼
process_entry.py collects all outputs:
    cleaned text
    token_dicts
    token_strings
    features = {
        token_count
        emotion_anchor_hits
        raw_emotion_hits
        embedding_emotion_distribution
        valence_arousal_summary
        sentiment
        repetition_weight
        crisis_flag
    }
    │
    ▼
core/nlp/__init__.py
    * exposes process_entry.py
    * exposes document_features / hooks to all NLP modules
    │
    ▼
External callers
    (app/routes/journal.py, app/helpers/display_last_entry.py, etc.)
```

---

### Notes on the diagram:

* `*` = Python module dependency
* `→` = data flow/output
* `process_entry.py` **does not call `emotion_analysis.py` directly** anymore.
* `emotion_analysis.py` is invoked **only inside `document_features(raw_text)`**, which is called by `text_processing.py`.
* `embeddings.py` is used **inside `emotion_analysis.py`**.
* Secondary modules (`pii.py`, `repetition_echo.py`, `sentiment_analysis.py`, `crisis.py`) feed directly into `process_entry.py`, not `text_processing.py`.


### Key Takeaways

1. **Single-entry embedding**: Always goes through `get_embedding_async`, which itself calls `batch_embeddings_async` for consistency.
2. **Batch embedding**: Handles multiple texts, preserves caching, reduces executor overhead.
3. **Cache**: `_embedding_cache` ensures identical texts never recompute embeddings.
4. **Model auto-detection**: `_load_model()` automatically finds the nested model folder in `models/roberta-large`.
5. **Error handling**: Zero vectors for empty/whitespace entries, and graceful fallback for embedding errors.

This map effectively isolates the embeddings “vertical slice” from input → features, so testing, debugging, or future refactors can be visualized without scanning unrelated modules.
