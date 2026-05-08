# jellyGPT AI Feature Benchmark

## Scope

This benchmark covers the current AI-facing and recommendation-facing behavior in jellyGPT.

Implemented behavior:

- `llm_rerank` appears in `GET /algorithms`.
- `llm_rerank` availability is controlled by `ENABLE_LLM_RERANK`.
- `POST /recommendations` ranks client-provided candidate metadata without Jellyfin credentials.
- `GET /recommendations` remains a cache-reader placeholder and does not call Ollama.
- Page-load-safe behavior is preserved: no LLM call, no SQLite scan, no generation during a recommendation API request.

## Environment notes

- Benchmark data is synthetic and contains no private Jellyfin library data or watch history.
- Ollama-backed reranking is not benchmarked here because it is not yet refined.

## Results summary

The synthetic benchmark in `bench_ai_features.py` runs 200 in-process calls per endpoint/case.

Typical current results:

- `GET /health`: around 1 ms mean latency.
- `GET /algorithms`: around 1 ms mean latency.
- `POST /recommendations` with a small synthetic candidate set: around 1.1-1.3 ms mean latency.
- Synthetic quality check: deterministic algorithms place the three relevant synthetic examples in the top three for the included benchmark case.

## Re-run

```bash
python bench_ai_features.py
```

## Next benchmark targets

Once actual Ollama clients/rerankers and cache workers are implemented, benchmark these separately:

1. Cache-read API latency: should stay low and not trigger generation.
2. Offline `llm_rerank` generation latency: allowed to be seconds because it is background work.
3. JSON validity rate from the selected model.
4. Quality delta versus `label_profile` and `blended` using rolling temporal holdout.
5. Fallback behavior when Ollama is unavailable, slow, or returns invalid output.
