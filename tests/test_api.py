import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from jellygpt.api import app


def test_health():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_algorithms_contains_blended():
    client = TestClient(app)
    response = client.get("/algorithms")
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["algorithms"]]
    assert "blended" in ids


def test_post_recommendations_ranks_candidates_from_watch_history():
    client = TestClient(app)
    payload = {
        "algo": "blended",
        "limit": 3,
        "now": "2026-05-08T12:00:00+00:00",
        "history": [
            {
                "item_name": "Rust self hosting tutorial",
                "total_count": 4,
                "total_time": 3600,
            }
        ],
        "candidates": [
            {
                "item_id": "rust-new",
                "title": "New Rust self hosting guide",
                "channel": "Local Dev",
                "content_kind": "video",
                "premiere_date": "2026-05-01T00:00:00+00:00",
            },
            {
                "item_id": "cooking-old",
                "title": "Classic cooking episode",
                "channel": "Kitchen",
                "content_kind": "video",
                "premiere_date": "2022-01-01T00:00:00+00:00",
            },
        ],
    }

    response = client.post("/recommendations", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["warning"] is None
    assert [item["item_id"] for item in data["items"]][:2] == ["rust-new", "cooking-old"]


def test_watch_context_prefers_similar_metadata_over_same_channel_filler():
    client = TestClient(app)
    payload = {
        "algo": "blended",
        "context": "watch",
        "limit": 3,
        "now": "2026-05-08T12:00:00+00:00",
        "current_item": {
            "item_id": "current",
            "title": "Quantum physics explained - Physics Channel",
            "channel": "Physics Channel",
            "content_kind": "video",
            "genres": ["Science"],
            "run_time_ticks": 18 * 60 * 10_000_000,
        },
        "queue_item_ids": ["queued"],
        "candidates": [
            {
                "item_id": "same-channel-filler",
                "title": "Weekly mailbag - Physics Channel",
                "channel": "Physics Channel",
                "content_kind": "video",
                "genres": ["Talk"],
                "premiere_date": "2026-05-07T00:00:00+00:00",
                "run_time_ticks": 18 * 60 * 10_000_000,
            },
            {
                "item_id": "similar-science",
                "title": "Quantum physics experiment explained",
                "channel": "Science Lab",
                "content_kind": "video",
                "genres": ["Science"],
                "premiere_date": "2026-01-01T00:00:00+00:00",
                "run_time_ticks": 20 * 60 * 10_000_000,
            },
            {
                "item_id": "queued",
                "title": "Quantum physics follow-up",
                "channel": "Science Lab",
                "content_kind": "video",
                "genres": ["Science"],
                "run_time_ticks": 20 * 60 * 10_000_000,
            },
        ],
    }

    response = client.post("/recommendations", json=payload)
    assert response.status_code == 200
    ranked_ids = [item["item_id"] for item in response.json()["items"]]
    assert ranked_ids[0] == "similar-science"
    assert "queued" not in ranked_ids


def test_watch_context_interleaves_large_same_channel_groups():
    client = TestClient(app)
    candidates = [
        {
            "item_id": f"snl-{idx}",
            "title": f"Weekend Update clip {idx}",
            "channel": "SNL",
            "content_kind": "video",
            "genres": ["Comedy"],
            "premiere_date": "2026-05-07T00:00:00+00:00",
            "run_time_ticks": 8 * 60 * 10_000_000,
        }
        for idx in range(1, 7)
    ]
    candidates.extend(
        [
            {
                "item_id": "late-night",
                "title": "Late night sketch comedy",
                "channel": "Late Night",
                "content_kind": "video",
                "genres": ["Comedy"],
                "premiere_date": "2026-05-06T00:00:00+00:00",
                "run_time_ticks": 8 * 60 * 10_000_000,
            },
            {
                "item_id": "standup",
                "title": "Standup comedy set",
                "channel": "Comedy Club",
                "content_kind": "video",
                "genres": ["Comedy"],
                "premiere_date": "2026-05-05T00:00:00+00:00",
                "run_time_ticks": 8 * 60 * 10_000_000,
            },
            {
                "item_id": "panel",
                "title": "Comedy panel highlights",
                "channel": "Panel Show",
                "content_kind": "video",
                "genres": ["Comedy"],
                "premiere_date": "2026-05-04T00:00:00+00:00",
                "run_time_ticks": 8 * 60 * 10_000_000,
            },
            {
                "item_id": "improv",
                "title": "Improv comedy scene",
                "channel": "Improv House",
                "content_kind": "video",
                "genres": ["Comedy"],
                "premiere_date": "2026-05-03T00:00:00+00:00",
                "run_time_ticks": 8 * 60 * 10_000_000,
            },
        ]
    )
    channels = {candidate["item_id"]: candidate["channel"] for candidate in candidates}
    payload = {
        "algo": "blended",
        "context": "watch",
        "limit": 8,
        "now": "2026-05-08T12:00:00+00:00",
        "current_item": {
            "item_id": "current",
            "title": "Weekend Update",
            "channel": "SNL",
            "content_kind": "video",
            "genres": ["Comedy"],
            "run_time_ticks": 8 * 60 * 10_000_000,
        },
        "candidates": candidates,
    }

    response = client.post("/recommendations", json=payload)

    assert response.status_code == 200
    ranked_ids = [item["item_id"] for item in response.json()["items"]]
    top_channels = [channels[item_id] for item_id in ranked_ids[:4]]
    assert top_channels.count("SNL") <= 2
    assert [channels[item_id] for item_id in ranked_ids].count("SNL") == 6


def test_watch_context_rotates_large_channel_groups_by_current_item():
    client = TestClient(app)
    candidates = [
        {
            "item_id": f"snl-{idx}",
            "title": f"Weekend Update clip {idx}",
            "channel": "SNL",
            "content_kind": "video",
            "genres": ["Comedy"],
            "premiere_date": "2026-05-07T00:00:00+00:00",
            "run_time_ticks": 8 * 60 * 10_000_000,
        }
        for idx in range(1, 17)
    ]
    candidates.extend(
        [
            {
                "item_id": f"other-{idx}",
                "title": f"Sketch comedy clip {idx}",
                "channel": f"Comedy Channel {idx}",
                "content_kind": "video",
                "genres": ["Comedy"],
                "premiere_date": "2026-05-01T00:00:00+00:00",
                "run_time_ticks": 8 * 60 * 10_000_000,
            }
            for idx in range(1, 7)
        ]
    )

    def ranked_snl_ids(current_id: str) -> list[str]:
        response = client.post(
            "/recommendations",
            json={
                "algo": "blended",
                "context": "watch",
                "limit": 12,
                "now": "2026-05-08T12:00:00+00:00",
                "current_item": {
                    "item_id": current_id,
                    "title": "Weekend Update",
                    "channel": "SNL",
                    "content_kind": "video",
                    "genres": ["Comedy"],
                    "run_time_ticks": 8 * 60 * 10_000_000,
                },
                "binge": {
                    "channel": "SNL",
                    "streak_count": 4,
                },
                "candidates": candidates,
            },
        )
        assert response.status_code == 200
        ranked_ids = [item["item_id"] for item in response.json()["items"]]
        return [item_id for item_id in ranked_ids if item_id.startswith("snl-")]

    first = ranked_snl_ids("current-a")
    second = ranked_snl_ids("current-b")

    assert len(first) >= 4
    assert len(second) >= 4
    assert first != second


def test_get_recommendations_reports_missing_index(monkeypatch, tmp_path):
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    client = TestClient(app)
    response = client.get("/recommendations?algo=blended&limit=3")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert "POST /index/refresh" in data["warning"]


def test_index_status_reads_cached_user_index(monkeypatch, tmp_path):
    write_test_index(tmp_path)
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))

    client = TestClient(app)
    response = client.get("/index/status?user_id=user-1")

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["user_id"] == "user-1"
    assert data["item_count"] == 5
    assert data["source_counts"] == {"video:Videos": 5}


def test_indexed_recommendations_rank_from_cache_without_candidates(monkeypatch, tmp_path):
    write_test_index(tmp_path)
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))

    client = TestClient(app)
    response = client.post(
        "/recommendations/indexed",
        json={
            "algo": "blended",
            "user_id": "user-1",
            "context": "watch",
            "limit": 3,
            "now": "2026-05-08T12:00:00+00:00",
            "current_item_id": "current",
            "queue_item_ids": ["queued"],
            "binge": {
                "channel": "Physics Channel",
                "streak_count": 3,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    ranked_ids = [item["item_id"] for item in data["items"]]
    assert ranked_ids[0] == "similar-science"
    assert "current" not in ranked_ids
    assert "queued" not in ranked_ids
    assert data["warning"] is None


def test_indexed_recommendations_filter_by_context(monkeypatch, tmp_path):
    write_test_index(tmp_path)
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))

    client = TestClient(app)
    response = client.post(
        "/recommendations/indexed",
        json={
            "algo": "blended",
            "user_id": "user-1",
            "context": "movie",
            "limit": 3,
        },
    )

    assert response.status_code == 200
    ranked_ids = [item["item_id"] for item in response.json()["items"]]
    assert ranked_ids == ["movie-1"]


def write_test_index(tmp_path):
    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "version": 1,
        "users": {
            "user-1": {
                "user_id": "user-1",
                "generated_at": generated_at,
                "server_url": "http://jellyfin.test",
                "source_counts": {"video:Videos": 5},
                "history": [
                    {
                        "item_name": "Quantum physics explained",
                        "total_count": 2,
                        "total_time": 1800,
                    }
                ],
                "items": [
                    indexed_candidate(
                        "current",
                        "Quantum physics explained - Physics Channel",
                        "Physics Channel",
                        genres=["Science"],
                    ),
                    indexed_candidate(
                        "same-channel-filler",
                        "Weekly mailbag - Physics Channel",
                        "Physics Channel",
                        genres=["Talk"],
                    ),
                    indexed_candidate(
                        "similar-science",
                        "Quantum physics experiment explained",
                        "Science Lab",
                        genres=["Science"],
                    ),
                    indexed_candidate(
                        "queued",
                        "Quantum physics follow-up",
                        "Science Lab",
                        genres=["Science"],
                    ),
                    indexed_candidate(
                        "movie-1",
                        "Documentary feature",
                        "Movies",
                        content_kind="movie",
                    ),
                ],
            }
        },
    }
    (tmp_path / "jellygpt-index.json").write_text(json.dumps(payload), encoding="utf-8")


def indexed_candidate(
    item_id: str,
    title: str,
    channel: str,
    *,
    content_kind: str = "video",
    genres: list[str] | None = None,
) -> dict:
    return {
        "item_id": item_id,
        "title": title,
        "type": "Movie" if content_kind == "movie" else "Video",
        "content_kind": content_kind,
        "channel": channel,
        "genres": genres or [],
        "premiere_date": "2026-05-01T00:00:00+00:00",
        "run_time_ticks": 18 * 60 * 10_000_000,
        "play_count": 0,
        "played": False,
        "playback_position_ticks": 0,
    }
