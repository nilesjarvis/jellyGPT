from __future__ import annotations

from .chunking import render_chunk_for_llm
from .markdown import looks_like_valid_update
from .models import WatchEvent
from .ollama import OllamaError, generate_with_ollama
from .prompts import CHUNK_SUMMARY_PROMPT, PROFILE_UPDATE_PROMPT


def summarize_chunk_fallback(events: list[WatchEvent]) -> str:
    total = len(events)
    long_watches = [event for event in events if (event.watched_seconds or 0) >= 20 * 60]
    short_watches = [
        event for event in events if event.watched_seconds is not None and event.watched_seconds < 45
    ]
    media_counts: dict[str, int] = {}
    for event in events:
        media_counts[event.media_type or "unknown"] = media_counts.get(event.media_type or "unknown", 0) + 1
    top_media = ", ".join(
        f"{key}: {value}" for key, value in sorted(media_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
    )
    examples = "\n".join(f"- {event.title} ({event.played_at.date()})" for event in events[:8])
    return f"""## Deterministic Watch-History Summary

- Events analyzed: {total}
- Longer watch sessions: {len(long_watches)}
- Very short sessions / likely skips: {len(short_watches)}
- Media-type mix: {top_media or 'unknown'}

## Evidence Notes

{examples or '- No events.'}
"""


def summarize_with_ollama(
    existing_profile: str,
    chunks: list[list[WatchEvent]],
    ollama_url: str,
    ollama_model: str,
) -> tuple[str, bool]:
    summaries: list[str] = []
    for chunk in chunks:
        prompt = CHUNK_SUMMARY_PROMPT.format(
            existing_profile=existing_profile[-4000:],
            chunk_text=render_chunk_for_llm(chunk),
        )
        summaries.append(generate_with_ollama(ollama_url, ollama_model, prompt))
    merge_prompt = PROFILE_UPDATE_PROMPT.format(
        existing_profile=existing_profile[-6000:],
        chunk_summaries="\n\n".join(summaries),
    )
    update = generate_with_ollama(ollama_url, ollama_model, merge_prompt)
    if not looks_like_valid_update(update):
        raise OllamaError("Ollama profile update failed validation")
    return update, True


def build_profile_update(
    existing_profile: str,
    chunks: list[list[WatchEvent]],
    ollama_url: str,
    ollama_model: str,
    require_ollama: bool = False,
) -> tuple[str, bool, str | None]:
    if not chunks:
        return "", False, None
    try:
        update, used_ollama = summarize_with_ollama(existing_profile, chunks, ollama_url, ollama_model)
        return update, used_ollama, None
    except Exception as exc:
        if require_ollama:
            raise
        fallback_sections = [summarize_chunk_fallback(chunk) for chunk in chunks]
        warning = f"Ollama unavailable or invalid; used deterministic fallback: {exc}"
        return "\n\n".join(fallback_sections), False, warning
