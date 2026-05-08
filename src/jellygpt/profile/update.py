from __future__ import annotations

from pathlib import Path

from jellygpt.config import Settings

from .chunking import chunk_watch_events
from .history import load_watch_events
from .markdown import append_update, extract_last_event_id, read_profile, write_profile_atomic
from .models import ProfileUpdateResult
from .summarizer import build_profile_update


def update_taste_profile(
    settings: Settings,
    user_id: str | None = None,
    since: str | None = None,
    profile_path: Path | None = None,
    require_ollama: bool | None = None,
    dry_run: bool = False,
) -> ProfileUpdateResult:
    path = profile_path or Path(settings.taste_profile_path)
    existing = read_profile(path, user_id=user_id)
    after_event_id = extract_last_event_id(existing)
    events = load_watch_events(
        Path(settings.playback_db),
        user_id=user_id,
        since=since,
        after_event_id=after_event_id,
        limit=settings.profile_max_events_per_run,
    )
    if not events:
        return ProfileUpdateResult(
            profile_path=str(path),
            user_id=user_id,
            events_seen=0,
            chunks_processed=0,
            updated=False,
            used_ollama=False,
            warning="No new watch events found.",
        )
    chunks = chunk_watch_events(events, max_events=settings.profile_chunk_events)
    update_md, used_ollama, warning = build_profile_update(
        existing,
        chunks,
        settings.ollama_url,
        settings.ollama_model,
        require_ollama=settings.profile_require_ollama if require_ollama is None else require_ollama,
    )
    last = events[-1]
    updated = append_update(
        existing,
        update_md,
        last_event_id=last.event_id,
        last_played_at=last.played_at.isoformat(),
    )
    if not dry_run:
        write_profile_atomic(path, updated)
    return ProfileUpdateResult(
        profile_path=str(path),
        user_id=user_id,
        events_seen=len(events),
        chunks_processed=len(chunks),
        updated=True,
        used_ollama=used_ollama,
        warning=warning,
        dry_run_markdown=updated if dry_run else None,
    )
