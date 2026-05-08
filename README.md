# jellyGPT

Optional recommendation and local-AI companion service for JellyTube/Jellyfin.

jellyGPT runs as a small sidecar API. JellyTube remains fully usable without it: if the service is unavailable, empty, or slow, the UI should fall back to JellyTube's built-in recommendation logic.

## Current status

- FastAPI service with `/health`, `/algorithms`, and recommendation endpoints.
- Deterministic recommendation scoring for `existing_logic_like`, `recency_popularity`, `label_profile`, and `blended`.
- Optional `llm_rerank` algorithm metadata for future Ollama-backed refinement.
- Indexed Jellyfin bridge via `POST /index/refresh` and `POST /recommendations/indexed`: jellyGPT can build a cached catalog and rank its own data from only the user, current item, and lightweight context.
- Backward-compatible reranking bridge via `POST /recommendations` for clients that still send bounded candidate sets.
- Cache-style `GET /recommendations` reads the current index without starting a slow refresh.

Ollama features are experimental and disabled by default. No LLM call is required to run the service.

## Goals

- Keep JellyTube fast and usable without this service.
- Keep slow database scans and optional AI/LLM work outside the JellyTube frontend.
- Support indexed recommendations where JellyTube does not have to send candidate lists.
- Keep a credential-free bridge where older clients can POST bounded candidates for ranking.
- Let users switch between recommendation algorithms in JellyTube.

## Non-goals

- No live LLM call during homepage render.
- No requirement that users install AI tooling.
- No write access to Jellyfin databases.
- No bundled private Jellyfin data, watch history, or API keys.

## Quick start: local development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
jellygpt serve --host 127.0.0.1 --port 8787
```

Then check:

```bash
curl http://127.0.0.1:8787/health
curl http://127.0.0.1:8787/algorithms
```

Run tests and lint:

```bash
pytest -q
ruff check src tests bench_ai_features.py bench_real_jellyfin.py
```

Run the synthetic benchmark:

```bash
python bench_ai_features.py
```

Run the real Jellyfin benchmark against your own server:

```bash
JELLYFIN_URL=http://jellyfin:8096 \
JELLYFIN_USERNAME=your-user \
JELLYFIN_PASSWORD=your-password \
CACHE_DIR=.cache-real \
python bench_real_jellyfin.py
```

The real benchmark refreshes the local index, exercises indexed home/movie/music/watch recommendations, and prints aggregate latency and quality checks without item titles.

## Interactive setup wizard

For self-hosters, jellyGPT includes a simple installer-style wizard:

```bash
./install.sh
```

or directly:

```bash
python3 install.py
```

On Windows:

```bat
install.bat
```

The wizard asks for local Jellyfin settings and writes local-only files:

```text
.env
docker-compose.local.yml
```

These files may contain private paths and API keys and are ignored by git.

## Minimal Docker Compose example

```yaml
services:
  jellygpt:
    image: ghcr.io/YOUR_GITHUB_USER_OR_ORG/jellygpt:latest
    ports:
      - "8787:8787"
    environment:
      JELLYFIN_URL: "http://jellyfin:8096"
      JELLYFIN_API_KEY: "${JELLYFIN_API_KEY}"
      # Or use JELLYFIN_USERNAME/JELLYFIN_PASSWORD for local testing.
      PLAYBACK_DB: "/jellyfin-data/playback_reporting.db"
      JELLYFIN_DB: "/jellyfin-data/jellyfin.db"
      INDEX_MAX_AGE_SECONDS: "3600"
      INDEX_LIMIT_PER_SOURCE: "5000"
      RECS_REFRESH_INTERVAL: "30m"
      ENABLE_LLM_RERANK: "false"
      ENABLE_PROFILE_UPDATES: "false"
      TASTE_PROFILE_PATH: "/cache/profiles/default.md"
      PROFILE_REFRESH_INTERVAL_SECONDS: "3600"
      OLLAMA_URL: "http://ollama:11434"
      OLLAMA_MODEL: "llama3.2:3b"
    volumes:
      - /path/to/jellyfin/data:/jellyfin-data:ro
      - jellygpt-cache:/cache

volumes:
  jellygpt-cache:
```

If you publish your own image, replace `YOUR_GITHUB_USER_OR_ORG` with your registry namespace.

## API overview

- `GET /health` — service status.
- `GET /algorithms` — algorithm metadata for UI selectors.
- `GET /recommendations` — read ranked recommendations from the current index without refreshing it.
- `POST /index/refresh` — refresh the cached Jellyfin index.
- `GET /index/status` — inspect index freshness and item counts.
- `POST /recommendations/indexed` — rank cached Jellyfin index data. JellyTube sends only the user/current item and lightweight context, not candidate lists.
- `POST /recommendations` — optional compatibility bridge. The client supplies candidate metadata and optional playback-history summaries; jellyGPT returns ranked item IDs and scores.

See `docs/api.md` for the full contract.

## Privacy model

This repository should contain source code, examples, and synthetic benchmarks only.

Do not commit:

- `.env`
- Jellyfin API keys
- Jellyfin databases
- Playback Reporting databases
- cached recommendation outputs from a real library
- taste-profile Markdown generated from personal watch history
- local service logs or private deployment notes

See `OPEN_SOURCE_NOTES.md` for the release audit notes.

## License

MIT. See `LICENSE`.
