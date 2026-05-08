from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from jellygpt.config import Settings
from jellygpt.profile.chunking import chunk_watch_events, render_chunk_for_llm
from jellygpt.profile.markdown import append_update, extract_last_event_id, initial_profile
from jellygpt.profile.models import WatchEvent
from jellygpt.profile.update import update_taste_profile


def test_append_update_preserves_existing_and_updates_marker():
    profile = initial_profile()
    profile += "\n- Old preference survives.\n"
    updated = append_update(profile, "## Evidence Notes\n\n- New update", "42", "2026-05-08T12:00:00")
    assert "Old preference survives" in updated
    assert "New update" in updated
    assert "<!-- jellygpt-last-event-id: 42 -->" in updated
    assert extract_last_event_id(updated) == "42"


def test_chunking_preserves_order_and_limits():
    events = [
        WatchEvent(event_id=str(i), played_at=datetime(2026, 5, 8, 12, i), item_id=str(i), title=f"Item {i}")
        for i in range(5)
    ]
    chunks = chunk_watch_events(events, max_events=2)
    assert [len(c) for c in chunks] == [2, 2, 1]
    rendered = render_chunk_for_llm(chunks[0])
    assert "Item 0" in rendered
    assert "Item 1" in rendered


def create_playback_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE PlaybackActivity(
            DateCreated TEXT,
            UserId TEXT,
            ItemId TEXT,
            ItemType TEXT,
            ItemName TEXT,
            PlaybackMethod TEXT,
            ClientName TEXT,
            DeviceName TEXT,
            PlayDuration INT
        )
        """
    )
    conn.executemany(
        "INSERT INTO PlaybackActivity VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("2026-05-08 10:00:00", "u1", "i1", "Video", "Long Watch", "Direct", "Jellyfin", "TV", 2400),
            ("2026-05-08 11:00:00", "u1", "i2", "Video", "Quick Skip", "Direct", "Jellyfin", "TV", 12),
        ],
    )
    conn.commit()
    conn.close()


def test_update_taste_profile_appends_fallback_summary(tmp_path: Path):
    db = tmp_path / "playback_reporting.db"
    profile = tmp_path / "profiles" / "default.md"
    create_playback_db(db)
    settings = Settings(
        playback_db=str(db),
        taste_profile_path=str(profile),
        ollama_url="http://127.0.0.1:9",
        profile_chunk_events=50,
    )
    result = update_taste_profile(settings, require_ollama=False)
    assert result.updated is True
    assert result.used_ollama is False
    assert result.events_seen == 2
    text = profile.read_text()
    assert "Long Watch" in text
    assert "Quick Skip" in text
    assert "Deterministic Watch-History Summary" in text

    second = update_taste_profile(settings, require_ollama=False)
    assert second.updated is False
    assert second.events_seen == 0
