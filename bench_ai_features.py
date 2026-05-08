#!/usr/bin/env python3
"""Benchmark jellyGPT recommendation endpoints and deterministic ranking quality."""
from __future__ import annotations

import json
import os
import statistics
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from jellygpt.api import app


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(len(values) - 1, round((len(values) - 1) * p))
    return values[idx]


def time_call(label: str, fn, n: int = 200) -> dict:
    durations = []
    statuses = []
    last_json = None
    for _ in range(n):
        start = time.perf_counter()
        response = fn()
        durations.append((time.perf_counter() - start) * 1000)
        statuses.append(response.status_code)
        try:
            last_json = response.json()
        except Exception:
            last_json = None
    return {
        "label": label,
        "runs": n,
        "status_codes": sorted(set(statuses)),
        "mean_ms": round(statistics.mean(durations), 3),
        "median_ms": round(statistics.median(durations), 3),
        "p95_ms": round(percentile(durations, 0.95), 3),
        "max_ms": round(max(durations), 3),
        "result_count": len((last_json or {}).get("items", [])),
        "warning": (last_json or {}).get("warning"),
    }


def synthetic_payload(algo: str, limit: int = 10) -> dict:
    return {
        "algo": algo,
        "limit": limit,
        "now": "2026-05-08T12:00:00+00:00",
        "recent_item_ids": ["watched-rust-1"],
        "history": [
            {"item_name": "Rust self hosting server setup", "total_count": 5, "total_time": 7200},
            {"item_name": "Crypto trading terminal build", "total_count": 3, "total_time": 3600},
            {"item_name": "Local AI homelab tutorial", "total_count": 2, "total_time": 2400},
        ],
        "candidates": [
            candidate(
                "rust-new",
                "New Rust self-hosting dashboard guide",
                "Local Dev",
                "2026-05-02",
            ),
            candidate(
                "ai-homelab",
                "Local AI homelab recommendations",
                "Self Hosted",
                "2026-04-20",
            ),
            candidate(
                "crypto-terminal",
                "Building a crypto trading terminal",
                "Trading Dev",
                "2026-03-15",
            ),
            candidate("cooking", "Classic soup cooking episode", "Kitchen", "2026-05-01"),
            candidate("travel", "Walking tour of Venice", "Travel Slow TV", "2025-01-01"),
            candidate("old-news", "Old politics panel discussion", "News Archive", "2022-01-01"),
        ],
    }


def watch_context_payload(algo: str, limit: int = 6) -> dict:
    return {
        "algo": algo,
        "context": "watch",
        "limit": limit,
        "now": "2026-05-08T12:00:00+00:00",
        "current_item": candidate(
            "current-physics",
            "Quantum physics explained - Physics Channel",
            "Physics Channel",
            "2026-05-01",
            genres=["Science"],
            run_time_minutes=18,
        ),
        "queue_item_ids": ["queued-physics"],
        "history": [
            {
                "item_name": "Quantum physics explained",
                "total_count": 2,
                "total_time": 1800,
                "latest_date": "2026-05-07T12:00:00+00:00",
            }
        ],
        "candidates": [
            candidate(
                "same-channel-filler",
                "Weekly mailbag - Physics Channel",
                "Physics Channel",
                "2026-05-07",
                genres=["Talk"],
                run_time_minutes=18,
            ),
            candidate(
                "similar-science",
                "Quantum physics experiment explained",
                "Science Lab",
                "2026-01-01",
                genres=["Science"],
                run_time_minutes=20,
            ),
            candidate(
                "similar-longform",
                "Quantum mechanics visual guide",
                "Deep Science",
                "2025-12-01",
                genres=["Science"],
                run_time_minutes=24,
            ),
            candidate(
                "queued-physics",
                "Quantum physics follow-up",
                "Science Lab",
                "2026-05-06",
                genres=["Science"],
                run_time_minutes=20,
            ),
            candidate("travel", "Walking tour of Venice", "Travel Slow TV", "2026-05-06"),
            candidate("cooking", "Classic soup cooking episode", "Kitchen", "2026-05-06"),
        ],
    }


def indexed_watch_payload(algo: str, limit: int = 6) -> dict:
    return {
        "algo": algo,
        "user_id": "bench-user",
        "context": "watch",
        "limit": limit,
        "now": "2026-05-08T12:00:00+00:00",
        "current_item_id": "current-physics",
        "queue_item_ids": ["queued-physics"],
        "binge": {
            "channel": "Physics Channel",
            "streak_count": 3,
        },
    }


def candidate(
    item_id: str,
    title: str,
    channel: str,
    premiere_date: str,
    *,
    genres: list[str] | None = None,
    run_time_minutes: int | None = None,
    play_count: int = 0,
    played: bool = False,
) -> dict:
    return {
        "item_id": item_id,
        "title": title,
        "channel": channel,
        "content_kind": "video",
        "genres": genres or [],
        "premiere_date": f"{premiere_date}T00:00:00+00:00",
        "run_time_ticks": run_time_minutes * 60 * 10_000_000 if run_time_minutes else None,
        "play_count": play_count,
        "played": played,
    }


def write_index(cache_dir: Path) -> None:
    payload = {
        "version": 1,
        "users": {
            "bench-user": {
                "user_id": "bench-user",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "server_url": "http://jellyfin.test",
                "source_counts": {"video:Videos": 7},
                "history": [
                    {"item_name": "Rust self hosting server setup", "total_count": 5, "total_time": 7200},
                    {"item_name": "Quantum physics explained", "total_count": 2, "total_time": 1800},
                    {"item_name": "Local AI homelab tutorial", "total_count": 2, "total_time": 2400},
                ],
                "items": [
                    candidate(
                        "current-physics",
                        "Quantum physics explained - Physics Channel",
                        "Physics Channel",
                        "2026-05-01",
                        genres=["Science"],
                        run_time_minutes=18,
                    ),
                    candidate(
                        "same-channel-filler",
                        "Weekly mailbag - Physics Channel",
                        "Physics Channel",
                        "2026-05-07",
                        genres=["Talk"],
                        run_time_minutes=18,
                    ),
                    candidate(
                        "similar-science",
                        "Quantum physics experiment explained",
                        "Science Lab",
                        "2026-01-01",
                        genres=["Science"],
                        run_time_minutes=20,
                    ),
                    candidate(
                        "similar-longform",
                        "Quantum mechanics visual guide",
                        "Deep Science",
                        "2025-12-01",
                        genres=["Science"],
                        run_time_minutes=24,
                    ),
                    candidate(
                        "queued-physics",
                        "Quantum physics follow-up",
                        "Science Lab",
                        "2026-05-06",
                        genres=["Science"],
                        run_time_minutes=20,
                    ),
                    candidate(
                        "ai-homelab",
                        "Local AI homelab recommendations",
                        "Self Hosted",
                        "2026-04-20",
                    ),
                    candidate("cooking", "Classic soup cooking episode", "Kitchen", "2026-05-01"),
                ],
            }
        },
    }
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "jellygpt-index.json").write_text(json.dumps(payload), encoding="utf-8")


def quality_case(client: TestClient, algo: str) -> dict:
    positives = {"rust-new", "ai-homelab", "crypto-terminal"}
    response = client.post("/recommendations", json=synthetic_payload(algo, limit=6))
    data = response.json()
    ranked = [item["item_id"] for item in data["items"]]
    top3 = ranked[:3]
    return {
        "algo": algo,
        "ranked": ranked,
        "recall_at_3": round(len(positives.intersection(top3)) / len(positives), 3),
        "first_irrelevant_rank": first_irrelevant_rank(ranked, positives),
    }


def indexed_context_quality_case(client: TestClient, algo: str) -> dict:
    positives = {"similar-science", "similar-longform", "same-channel-filler"}
    response = client.post("/recommendations/indexed", json=indexed_watch_payload(algo, limit=6))
    data = response.json()
    ranked = [item["item_id"] for item in data["items"]]
    top3 = ranked[:3]
    return {
        "algo": algo,
        "ranked": ranked,
        "recall_at_3": round(len(positives.intersection(top3)) / len(positives), 3),
        "current_excluded": "current-physics" not in ranked,
        "queue_excluded": "queued-physics" not in ranked,
        "warning": data.get("warning"),
    }


def context_quality_case(client: TestClient, algo: str) -> dict:
    positives = {"similar-science", "similar-longform"}
    response = client.post("/recommendations", json=watch_context_payload(algo, limit=6))
    data = response.json()
    ranked = [item["item_id"] for item in data["items"]]
    top2 = ranked[:2]
    return {
        "algo": algo,
        "ranked": ranked,
        "recall_at_2": round(len(positives.intersection(top2)) / len(positives), 3),
        "first_irrelevant_rank": first_irrelevant_rank(ranked, positives),
        "queue_excluded": "queued-physics" not in ranked,
    }


def first_irrelevant_rank(ranked: list[str], positives: set[str]) -> int | None:
    return next(
        (idx + 1 for idx, item_id in enumerate(ranked) if item_id not in positives),
        None,
    )


def run_case() -> dict:
    os.environ["ENABLE_LLM_RERANK"] = "false"
    with tempfile.TemporaryDirectory(prefix="jellygpt-bench-") as cache_dir:
        os.environ["CACHE_DIR"] = cache_dir
        write_index(Path(cache_dir))
        client = TestClient(app)
        return {
            "enable_llm_rerank": False,
            "latency": [
                time_call("GET /health", lambda: client.get("/health")),
                time_call("GET /algorithms", lambda: client.get("/algorithms")),
                time_call(
                    "POST /recommendations blended synthetic",
                    lambda: client.post(
                        "/recommendations",
                        json=synthetic_payload("blended", limit=10),
                    ),
                ),
                time_call(
                    "POST /recommendations blended watch context",
                    lambda: client.post(
                        "/recommendations",
                        json=watch_context_payload("blended", limit=10),
                    ),
                ),
                time_call(
                    "POST /recommendations/indexed blended watch context",
                    lambda: client.post(
                        "/recommendations/indexed",
                        json=indexed_watch_payload("blended", limit=10),
                    ),
                ),
            ],
            "quality": [
                quality_case(client, algo)
                for algo in ["existing_logic_like", "recency_popularity", "label_profile", "blended"]
            ],
            "context_quality": [
                context_quality_case(client, algo)
                for algo in ["existing_logic_like", "recency_popularity", "label_profile", "blended"]
            ],
            "indexed_context_quality": [
                indexed_context_quality_case(client, algo)
                for algo in ["existing_logic_like", "recency_popularity", "label_profile", "blended"]
            ],
        }


def main() -> None:
    result = {
        "benchmark": "jellyGPT active optional recommendation integration",
        "notes": [
            "POST /recommendations remains available for client-provided reranking.",
            "POST /recommendations/indexed ranks cached Jellyfin index data without client candidates.",
            (
                "JellyTube can consume these ranked item ids and fall back to built-in "
                "ranking on error/empty output."
            ),
            (
                "llm_rerank is intentionally omitted from this deterministic benchmark."
            ),
        ],
        "cases": [run_case()],
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
