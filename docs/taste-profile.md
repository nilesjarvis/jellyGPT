# AI Taste Profile

jellyGPT includes an optional periodic feature that uses Ollama to maintain a long-term Markdown taste profile from the user's Jellyfin Playback Reporting history.

## Purpose

The profile is meant to capture durable recommendation knowledge that is hard to express with simple counters:

- stable taste preferences
- emerging interests
- negative/skip signals
- watch-time patterns
- format preferences
- recommendation guidance
- uncertainty and weak signals

The profile is stored as Markdown for now so users can inspect and edit it.

Default path:

```text
/cache/profiles/default.md
```

## Important behavior

The profile updater is incremental. It does **not** blindly replace the Markdown file with a new LLM output.

Instead it:

1. reads the existing profile
2. reads only new Playback Reporting events after the last processed marker
3. chunks watch history into LLM-safe blocks
4. asks Ollama for concise Markdown evidence summaries
5. validates the result
6. appends a dated update section
7. updates marker comments for the last processed event/time

If Ollama fails and `PROFILE_REQUIRE_OLLAMA=false`, jellyGPT writes a deterministic fallback summary instead of failing the job.

## CLI usage

Run one update:

```bash
jellygpt profile update
```

Dry run without writing:

```bash
jellygpt profile update --dry-run
```

Require Ollama and fail if unavailable:

```bash
jellygpt profile update --require-ollama
```

Run the periodic worker:

```bash
jellygpt worker profile-loop
```

Show the current profile:

```bash
jellygpt profile show
```

## Environment

```env
ENABLE_PROFILE_UPDATES=true
TASTE_PROFILE_PATH=/cache/profiles/default.md
PROFILE_REFRESH_INTERVAL_SECONDS=3600
PROFILE_CHUNK_EVENTS=50
PROFILE_MAX_EVENTS_PER_RUN=1000
PROFILE_REQUIRE_OLLAMA=false
OLLAMA_URL=http://ollama:11434
OLLAMA_MODEL=llama3.2:3b
```

## Prompt strategy

jellyGPT uses a map/reduce/refine pattern:

1. **Map:** summarize each chunk of watch history.
2. **Reduce/refine:** merge chunk summaries into one concise profile update.
3. **Append:** store the update in the Markdown file rather than replacing the file.

The prompts instruct the model to:

- output Markdown only
- avoid JSON
- avoid invented titles/preferences
- separate stable signals from weak signals
- treat high completion/rewatches as positive
- treat very short plays as skips/negative signals
- include uncertainty when evidence is thin

## Reliability limits

Small local models can be inconsistent, so jellyGPT avoids depending on perfect model output:

- no LLM call happens during page load
- no recommendation endpoint waits on this feature
- invalid/empty Ollama responses are rejected
- deterministic fallback summaries keep the profile moving
- the existing profile is preserved
