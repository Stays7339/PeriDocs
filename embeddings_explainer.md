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

If you like, I can also **draft a mini “vertical module map” for the embeddings pipeline** that connects this file directly to `process_entry.py` and `emotion_analysis.py`—kind of like a zoomed-in PeriDocs NLP pipeline diagram. It makes onboarding and testing much easier.

Do you want me to do that next?


Perfect. Here’s a **focused “zoomed-in” PeriDocs NLP embeddings pipeline map**, showing exactly how `embeddings.py` interacts with `process_entry.py` and `emotion_analysis.py`. This is meant to complement your full ASCII map but isolates the embedding flow for clarity.

```
Raw Text Input
    │
    ▼
process_entry.py
    ├─ text_processing.py.clean_text
    ├─ text_processing.py.tokenize_text
    ├─ pii.py.redact_pii
    ├─ repetition_echo.py.weight_repetition
    ├─ sentiment_analysis.py.analyze_sentiment
    └─ crisis.py.detect_crisis
    │
    ▼
emotion_analysis.py.analyze_emotions(raw_text)
    │
    ├─ _lexicon_emotion_features(tokens)
    │    └─ detect_emotion_tokens(tokens)
    │         ├─ anchors.py._EMOTION_LEXICONS
    │         ├─ fuzzy_utils.py.get_combined_lexicons
    │         └─ fuzzy_utils.py.fuzzy_matches_above
    │
    ├─ compute emotion distribution
    │
    └─ call embeddings.py.embed_entry_text(raw_text, pii_text)
             │
             ├─ get_embedding_async(raw_text)
             │    ├─ check _embedding_cache
             │    ├─ use batch_embeddings_async([text]) internally
             │    └─ zero vector if empty / whitespace
             │
             ├─ batch_embeddings_async(texts)
             │    ├─ ensure model loaded via _load_model()
             │    ├─ executor batch processing (_embed_sync)
             │    └─ cache results in _embedding_cache
             │
             ├─ _embed_sync(text)
             │    └─ SentenceTransformer.encode(..., normalize_embeddings=True)
             │
             └─ returns embedding vector → emotion_analysis.py
    │
    ▼
emotion_analysis.py
    ├─ compute embedding-weighted emotion distribution
    └─ valence/arousal summary
    │
    ▼
process_entry.py
    └─ aggregates:
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
External Callers
(app/routes/journal.py, helpers/display_last_entry.py, etc.)
```

### Key Takeaways

1. **Single-entry embedding**: Always goes through `get_embedding_async`, which itself calls `batch_embeddings_async` for consistency.
2. **Batch embedding**: Handles multiple texts, preserves caching, reduces executor overhead.
3. **Cache**: `_embedding_cache` ensures identical texts never recompute embeddings.
4. **Model auto-detection**: `_load_model()` automatically finds the nested model folder in `models/roberta-large`.
5. **Error handling**: Zero vectors for empty/whitespace entries, and graceful fallback for embedding errors.

This map effectively isolates the embeddings “vertical slice” from input → features, so testing, debugging, or future refactors can be visualized without scanning unrelated modules.

I can also **propose a modular split for embeddings.py** that keeps this vertical flow intact but reduces the single-file 214-line complexity. That would make `_load_model`, caching, and async/sync wrappers separate logical units.

Do you want me to draft that modular split next?
