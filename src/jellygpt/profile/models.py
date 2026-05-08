from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class WatchEvent:
    event_id: str
    played_at: datetime
    item_id: str
    title: str
    user_id: str | None = None
    media_type: str | None = None
    watched_seconds: int | None = None
    runtime_seconds: int | None = None
    completion_ratio: float | None = None


@dataclass(frozen=True)
class ProfileUpdateResult:
    profile_path: str
    user_id: str | None
    events_seen: int
    chunks_processed: int
    updated: bool
    used_ollama: bool
    warning: str | None = None
    dry_run_markdown: str | None = None
