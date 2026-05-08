# jellyGPT Architecture

jellyGPT is an optional sidecar service for JellyTube/Jellyfin.

## Data flow

Current active integration:

```text
JellyTube loaded items + playback summary -> jellyGPT POST /recommendations -> ranked item IDs -> JellyTube UI
```

Future cached integration:

```text
Jellyfin DBs/API -> jellyGPT offline generator -> cached JSON -> jellyGPT GET /recommendations -> JellyTube UI
```

## Speed rule

JellyTube must never depend on slow jellyGPT work. If jellyGPT is unavailable, times out, or returns no useful items, JellyTube falls back to built-in recommendation logic.

The current `POST /recommendations` bridge is intended to be fast and deterministic. It receives a bounded candidate set from the client and returns ranked IDs; it should not perform live SQLite scans or LLM calls.

Background workers may later do slow work, including:

- SQLite scans
- media labeling
- benchmark runs
- Ollama generation
- cache refreshes

## Main modules

- `api`: FastAPI app for JellyTube and health checks.
- `schemas`: Pydantic request/response models.
- `algorithms`: deterministic recommendation strategies.
- `config`: environment-driven settings.
- `cli`: command-line entry points.

Planned modules:

- `ingest`: load Jellyfin metadata and Playback Reporting rows.
- `labels`: deterministic media labeling plus optional LLM label enrichment.
- `cache`: read/write generated artifacts.
- `benchmark`: temporal holdout evaluation.
- `worker`: scheduled cache refresh.

## Recommended default algorithm

Start with `blended`, which combines newness, completion/watch-history signals, channel affinity, label/genre affinity, and recent-play penalties.

The current implementation is deterministic and transparent. `llm_rerank` is exposed as optional metadata for future Ollama-backed refinement, but it should remain outside the page-load critical path.

## Failure behavior

If jellyGPT is unavailable, JellyTube falls back to its built-in recommendation logic.
