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
        "history": [{"item_name": "Rust self hosting tutorial", "total_count": 4, "total_time": 3600}],
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


def test_get_recommendations_remains_cache_placeholder():
    client = TestClient(app)
    response = client.get("/recommendations?algo=blended&limit=3")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert "POST /recommendations" in data["warning"]
