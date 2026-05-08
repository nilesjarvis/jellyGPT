from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .models import WatchEvent


def parse_datetime(value: str) -> datetime:
    value = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.strptime(value.split(".")[0], "%Y-%m-%d %H:%M:%S")


def load_watch_events(
    playback_db: Path,
    user_id: str | None = None,
    since: str | None = None,
    after_event_id: str | None = None,
    limit: int = 1000,
) -> list[WatchEvent]:
    if not playback_db.exists():
        return []
    conditions: list[str] = []
    params: list[object] = []
    if user_id:
        conditions.append("UserId = ?")
        params.append(user_id)
    if since:
        conditions.append("DateCreated > ?")
        params.append(since)
    # PlaybackActivity has no stable numeric id in some installs, so use rowid.
    if after_event_id and str(after_event_id).isdigit():
        conditions.append("rowid > ?")
        params.append(int(after_event_id))
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    query = f"""
        SELECT rowid, DateCreated, UserId, ItemId, ItemType, ItemName, PlayDuration
        FROM PlaybackActivity
        {where}
        ORDER BY DateCreated ASC, rowid ASC
        LIMIT ?
    """
    params.append(limit)
    conn = sqlite3.connect(f"file:{playback_db}?mode=ro", uri=True)
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    events: list[WatchEvent] = []
    for rowid, date_created, uid, item_id, item_type, item_name, play_duration in rows:
        watched = int(play_duration) if play_duration is not None else None
        events.append(
            WatchEvent(
                event_id=str(rowid),
                played_at=parse_datetime(str(date_created)),
                user_id=uid,
                item_id=str(item_id or ""),
                title=str(item_name or "Unknown item"),
                media_type=str(item_type or "unknown"),
                watched_seconds=watched,
                runtime_seconds=None,
                completion_ratio=None,
            )
        )
    return events
