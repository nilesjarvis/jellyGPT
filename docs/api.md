# jellyGPT API Contract

Base URL example:

```text
http://jellygpt:8787
```

## `GET /health`

Returns service status.

```json
{
  "ok": true,
  "version": "0.1.0"
}
```

## `GET /algorithms`

Returns algorithms that a UI can display.

```json
{
  "algorithms": [
    {"id": "existing_logic_like", "name": "Existing JellyTube", "available": true},
    {"id": "recency_popularity", "name": "Recency / Popularity", "available": true},
    {"id": "label_profile", "name": "Label Profile", "available": true},
    {"id": "blended", "name": "Blended", "available": true},
    {"id": "llm_rerank", "name": "AI Rerank", "available": false, "reason": "Ollama reranking disabled"}
  ]
}
```

## `POST /recommendations`

Compatibility ranking bridge. The client provides a bounded set of already-loaded candidates and optional playback-history summaries. jellyGPT returns ranked item IDs that the client maps back to its local media items.

This endpoint does not require Jellyfin credentials.

Request:

```json
{
  "algo": "blended",
  "user_id": "optional-client-user-id",
  "context": "watch",
  "limit": 50,
  "now": "2026-05-08T12:00:00Z",
  "recent_item_ids": ["recent-item-id"],
  "queue_item_ids": ["already-queued-item-id"],
  "binge": {
    "channel": "Example Channel",
    "series_id": null,
    "streak_count": 3
  },
  "current_item": {
    "item_id": "currently-playing-id",
    "title": "Currently playing video",
    "type": "Video",
    "content_kind": "video",
    "channel": "Example Channel",
    "series_id": null,
    "parent_id": null,
    "genres": ["Technology"],
    "date_created": "2026-05-01T00:00:00Z",
    "premiere_date": "2026-04-30T00:00:00Z",
    "last_played_date": null,
    "run_time_ticks": 6000000000,
    "play_count": 0,
    "played": false,
    "playback_position_ticks": 0
  },
  "history": [
    {
      "item_name": "Example show or video title",
      "total_count": 3,
      "total_time": 3600,
      "latest_date": "2026-05-08T10:00:00Z"
    }
  ],
  "candidates": [
    {
      "item_id": "abc123",
      "title": "Example video",
      "type": "Video",
      "content_kind": "video",
      "channel": "Example Channel",
      "series_id": null,
      "parent_id": null,
      "genres": ["Technology"],
      "date_created": "2026-05-01T00:00:00Z",
      "premiere_date": "2026-04-30T00:00:00Z",
      "last_played_date": null,
      "run_time_ticks": 6000000000,
      "play_count": 0,
      "played": false,
      "playback_position_ticks": 0
    }
  ]
}
```

`context`, `current_item`, and `queue_item_ids` are optional. When present, jellyGPT uses
them to rerank watch-page recommendations around the currently playing item and to keep queued
items out of the returned rail.

## `POST /index/refresh`

Refreshes the cached Jellyfin index. jellyGPT uses `JELLYFIN_URL` plus either
`JELLYFIN_API_KEY` or `JELLYFIN_USERNAME`/`JELLYFIN_PASSWORD`.

Request:

```json
{
  "user_id": "optional-jellyfin-user-id"
}
```

Response:

```json
{
  "available": true,
  "generated_at": "2026-05-08T12:00:00Z",
  "cache_age_seconds": 0,
  "user_id": "jellyfin-user-id",
  "item_count": 1541,
  "history_count": 42,
  "source_counts": {
    "video:Shows": 800,
    "movie:Movies": 200
  },
  "warning": null
}
```

## `GET /index/status?user_id=...`

Reads cache freshness and counts without contacting Jellyfin.

## `POST /recommendations/indexed`

Primary JellyTube integration. The client does not send a candidate list. jellyGPT ranks items
from its cached Jellyfin index using the current item, user id, recent/queue exclusions, and
optional binge context.

Request:

```json
{
  "algo": "blended",
  "user_id": "jellyfin-user-id",
  "context": "watch",
  "limit": 28,
  "current_item_id": "currently-playing-id",
  "current_item": {
    "item_id": "currently-playing-id",
    "title": "Currently playing video",
    "type": "Video",
    "content_kind": "video",
    "channel": "Example Channel",
    "series_id": null,
    "parent_id": null,
    "genres": ["Technology"]
  },
  "recent_item_ids": ["recent-item-id"],
  "queue_item_ids": ["already-queued-item-id"],
  "binge": {
    "channel": "Example Channel",
    "series_id": null,
    "streak_count": 3
  }
}
```

`context` filters the indexed catalog before scoring:

- `home` ranks non-movie videos/music videos.
- `movie` ranks movies.
- `music` ranks music videos.
- `watch` ranks movies only for a movie current item, otherwise non-movie items.

Response shape is the same as `POST /recommendations`.

Response:

```json
{
  "algo": "blended",
  "generated_at": "2026-05-08T12:00:00Z",
  "cache_age_seconds": 0,
  "items": [
    {
      "item_id": "abc123",
      "score": 42.7,
      "reason": "matches watch history"
    }
  ],
  "warning": null
}
```

## `GET /recommendations?algo=blended&user_id=...&limit=50`

Reads ranked recommendations from the current index without triggering slow refresh work. If no index is present, it returns an empty list and a warning.

```json
{
  "algo": "blended",
  "generated_at": null,
  "cache_age_seconds": null,
  "items": [],
  "warning": "No jellyGPT index is available yet; run POST /index/refresh."
}
```
