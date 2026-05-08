# Self-hosting jellyGPT


## Interactive installer

The easiest path should be:

```bash
./install.sh
```

This runs `install.py`, asks the user for the required Jellyfin and recommendation settings, and generates:

```text
.env
docker-compose.local.yml
```

The generated compose file mounts the Jellyfin data directory read-only and stores jellyGPT output in a named Docker volume.

The installer is deliberately simple and dependency-light: it only needs Python 3 and Docker/Compose to actually start the service.

## Requirements

- Running Jellyfin server.
- Playback Reporting plugin installed and populated.
- Read-only access to Jellyfin data directory.
- Optional: Ollama for local AI reranking/label enrichment.

## Bare minimum

Run JellyTube alone. jellyGPT is not required.

## Enhanced recommendations

Run jellyGPT next to Jellyfin and point JellyTube at it with:

```env
JELLYGPT_URL=http://jellygpt:8787
```

Mount Jellyfin data read-only:

```yaml
volumes:
  - /var/lib/jellyfin/data:/jellyfin-data:ro
```

If your Jellyfin Docker container uses `/config/data`, mount that host folder instead.

## Optional AI

Run Ollama and enable:

```env
ENABLE_LLM_RERANK=true
OLLAMA_URL=http://ollama:11434
OLLAMA_MODEL=llama3.2:3b
```

AI is optional and should only run offline/background work.

## Periodic AI taste-profile worker

If enabled by the installer, `docker-compose.local.yml` includes a second service:

```text
jellygpt-profile-worker
```

It runs:

```bash
jellygpt worker profile-loop
```

The worker periodically reads Playback Reporting history and asks Ollama to append a Markdown taste-profile update at:

```text
/cache/profiles/default.md
```

Manual one-shot command:

```bash
jellygpt profile update --require-ollama
```

Dry-run command:

```bash
jellygpt profile update --dry-run
```

This feature is intentionally separate from the recommendation API. JellyTube should not wait on this worker during page load.
