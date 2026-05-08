from __future__ import annotations

from .models import WatchEvent


def chunk_watch_events(events: list[WatchEvent], max_events: int = 50, max_chars: int = 6000) -> list[list[WatchEvent]]:
    chunks: list[list[WatchEvent]] = []
    current: list[WatchEvent] = []
    current_chars = 0
    for event in sorted(events, key=lambda e: (e.played_at, e.event_id)):
        rendered = render_event(event)
        if current and (len(current) >= max_events or current_chars + len(rendered) > max_chars):
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(event)
        current_chars += len(rendered)
    if current:
        chunks.append(current)
    return chunks


def render_event(event: WatchEvent) -> str:
    completion = "unknown"
    if event.completion_ratio is not None:
        completion = f"{event.completion_ratio:.0%}"
    watched = f"{event.watched_seconds}s" if event.watched_seconds is not None else "unknown"
    runtime = f"{event.runtime_seconds}s" if event.runtime_seconds is not None else "unknown"
    return (
        f"- {event.played_at.isoformat()} | {event.media_type or 'unknown'} | "
        f"{event.title} | watched={watched} | runtime={runtime} | completion={completion}"
    )


def render_chunk_for_llm(events: list[WatchEvent]) -> str:
    return "\n".join(render_event(event) for event in events)
