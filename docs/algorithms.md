# Recommendation Algorithms

## `existing_logic_like`

Approximation of JellyTube's built-in recommendation behavior. Used as a baseline and fallback-oriented mode.

Current signals include played/unplayed state, item age, recent-play penalties, channel affinity, and simple metadata matches.

## `recency_popularity`

Prioritizes newer items and frequently played/engaged items. It is fast and deterministic, with penalties for items that were played very recently.

## `label_profile`

Current implementation: deterministic profile-style scoring from caller-provided candidate metadata and playback-history summaries. It uses channel, series, genre, and title-token overlap as lightweight taste signals.

Future cached implementation: can incorporate richer precomputed media labels and engagement-weighted playback history from background workers.

## `blended`

Recommended enhanced default. Combines newness, unplayed preference, channel/series affinity, genre/title overlap, and recent-play penalties.

## `llm_rerank`

Optional experimental mode. The algorithm is advertised only when enabled, but current runtime behavior still uses deterministic scoring unless a future Ollama reranker is implemented. Any real LLM work should happen offline or outside the page-load critical path.
