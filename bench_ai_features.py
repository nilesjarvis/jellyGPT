#!/usr/bin/env python3
"""Benchmark jellyGPT recommendation endpoints and deterministic ranking quality."""
from __future__ import annotations

import json
import os
import statistics
import time

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
            candidate("rust-new", "New Rust self-hosting dashboard guide", "Local Dev", "2026-05-02"),
            candidate("ai-homelab", "Local AI homelab recommendations", "Self Hosted", "2026-04-20"),
            candidate("crypto-terminal", "Building a crypto trading terminal", "Trading Dev", "2026-03-15"),
            candidate("cooking", "Classic soup cooking episode", "Kitchen", "2026-05-01"),
            candidate("travel", "Walking tour of Venice", "Travel Slow TV", "2025-01-01"),
            candidate("old-news", "Old politics panel discussion", "News Archive", "2022-01-01"),
        ],
    }


def candidate(item_id: str, title: str, channel: str, premiere_date: str) -> dict:
    return {
        "item_id": item_id,
        "title": title,
        "channel": channel,
        "content_kind": "video",
        "premiere_date": f"{premiere_date}T00:00:00+00:00",
        "play_count": 0,
        "played": False,
    }


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
        "first_irrelevant_rank": next((idx + 1 for idx, item_id in enumerate(ranked) if item_id not in positives), None),
    }


def run_case(enable_llm: bool) -> dict:
    os.environ["ENABLE_LLM_RERANK"] = "true" if enable_llm else "false"
    client = TestClient(app)
    return {
        "enable_llm_rerank": enable_llm,
        "latency": [
            time_call("GET /health", lambda: client.get("/health")),
            time_call("GET /algorithms", lambda: client.get("/algorithms")),
            time_call(
                "POST /recommendations blended synthetic",
                lambda: client.post("/recommendations", json=synthetic_payload("blended", limit=10)),
            ),
        ],
        "quality": [quality_case(client, algo) for algo in ["existing_logic_like", "recency_popularity", "label_profile", "blended"]],
    }


def main() -> None:
    result = {
        "benchmark": "jellyGPT active optional recommendation integration",
        "notes": [
            "POST /recommendations ranks client-provided candidates without Jellyfin credentials.",
            "JellyTube can consume these ranked item ids and fall back to built-in ranking on error/empty output.",
            "llm_rerank remains a metadata-gated option; no live LLM calls are in the page-render path.",
        ],
        "cases": [run_case(False), run_case(True)],
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
