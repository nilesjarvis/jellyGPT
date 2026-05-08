# jellyGPT

Optional recommendation and local-AI companion service for JellyTube/Jellyfin.

jellyGPT runs as a small sidecar API. JellyTube remains fully usable without it: if the service is unavailable, empty, or slow, the UI should fall back to JellyTube's built-in recommendation logic.

## Current status

- FastAPI service with `/health`, `/algorithms`, and recommendation endpoints.
- Deterministic recommendation scoring for `existing_logic_like`, `recency_popularity`, `label_profile`, and `blended`.
- Optional `llm_rerank` algorithm metadata for future Ollama-backed refinement.
- Active JellyTube bridge via `POST /recommendations`: JellyTube can send an already-loaded candidate set and playback-history summary, and jellyGPT returns ranked item IDs.
- Legacy/cache-style `GET /recommendations` is intentionally still a placeholder until background cache generation is implemented.

Ollama features are experimental and disabled by default. No LLM call is required to run the service.

## Goals

- Keep JellyTube fast and usable without this service.
- Keep slow database scans and optional AI/LLM work outside the JellyTube frontend.
- Support a credential-free bridge where JellyTube can POST bounded candidates for ranking.
- Support future offline/cache generation for larger self-hosted deployments.
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
ruff check src tests bench_ai_features.py
```

Run the synthetic benchmark:

```bash
python bench_ai_features.py
```

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
      PLAYBACK_DB: "/jellyfin-data/playback_reporting.db"
      JELLYFIN_DB: "/jellyfin-data/jellyfin.db"
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
- `GET /recommendations` — future cached recommendation reader; currently returns an empty placeholder response.
- `POST /recommendations` — active optional ranking bridge. The client supplies candidate metadata and optional playback-history summaries; jellyGPT returns ranked item IDs and scores.

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
