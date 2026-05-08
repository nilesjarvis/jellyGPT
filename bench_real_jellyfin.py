#!/usr/bin/env python3
"""Benchmark indexed jellyGPT recommendations against a real Jellyfin server.

Configuration is read from environment variables:

  JELLYFIN_URL, plus either JELLYFIN_API_KEY or JELLYFIN_USERNAME/JELLYFIN_PASSWORD.

The output avoids item titles and credentials; it reports aggregate counts,
latency, and structural quality checks.
"""
from __future__ import annotations

import json
import os
import statistics
import time
from collections import Counter
from typing import Any

from fastapi.testclient import TestClient

from jellygpt.api import app
from jellygpt.config import get_settings
from jellygpt.indexer import JellyfinIndexService, candidates_from_index
from jellygpt.schemas import RecommendationCandidate


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, round((len(ordered) - 1) * p))
    return ordered[idx]


def summarize_durations(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean_ms": 0.0, "median_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    return {
        "mean_ms": round(statistics.mean(values), 3),
        "median_ms": round(statistics.median(values), 3),
        "p95_ms": round(percentile(values, 0.95), 3),
        "max_ms": round(max(values), 3),
    }


def time_endpoint(client: TestClient, label: str, payload: dict[str, Any], runs: int) -> dict[str, Any]:
    durations: list[float] = []
    statuses: list[int] = []
    warnings: Counter[str] = Counter()
    result_counts: list[int] = []
    last_json: dict[str, Any] = {}
    for _ in range(runs):
        start = time.perf_counter()
        response = client.post("/recommendations/indexed", json=payload)
        durations.append((time.perf_counter() - start) * 1000)
        statuses.append(response.status_code)
        data = response.json()
        last_json = data
        result_counts.append(len(data.get("items", [])))
        if data.get("warning"):
            warnings[str(data["warning"])] += 1
    return {
        "label": label,
        "runs": runs,
        "status_codes": sorted(set(statuses)),
        **summarize_durations(durations),
        "min_result_count": min(result_counts) if result_counts else 0,
        "max_result_count": max(result_counts) if result_counts else 0,
        "warnings": dict(warnings),
        "last_quality": quality_summary(last_json, payload, indexed_items()),
    }


def indexed_items() -> dict[str, RecommendationCandidate]:
    settings = get_settings()
    service = JellyfinIndexService(settings)
    user_index = service.load_user_index()
    if not user_index:
        return {}
    return {candidate.item_id: candidate for candidate in candidates_from_index(user_index)}


def quality_summary(
    response: dict[str, Any],
    payload: dict[str, Any],
    by_id: dict[str, RecommendationCandidate],
) -> dict[str, Any]:
    returned_ids = [item.get("item_id") for item in response.get("items", []) if item.get("item_id")]
    returned = [by_id[item_id] for item_id in returned_ids if item_id in by_id]
    current_id = payload.get("current_item_id")
    queue_ids = set(payload.get("queue_item_ids") or [])
    top10 = returned[:10]
    top10_channels = {candidate.channel for candidate in top10 if candidate.channel}
    current = by_id.get(current_id) if current_id else None
    current_channel = current.channel if current else None
    current_genres = set(current.genres or []) if current else set()
    return {
        "result_count": len(returned_ids),
        "duplicate_ids": len(returned_ids) - len(set(returned_ids)),
        "missing_from_index": len([item_id for item_id in returned_ids if item_id not in by_id]),
        "current_returned": current_id in returned_ids if current_id else False,
        "queued_returned": bool(queue_ids.intersection(returned_ids)),
        "top10_distinct_channels": len(top10_channels),
        "top10_same_channel": sum(
            1 for candidate in top10 if current_channel and candidate.channel == current_channel
        ),
        "top10_genre_overlap": sum(
            1 for candidate in top10 if current_genres.intersection(candidate.genres or [])
        ),
    }


def aggregate_watch_quality(
    payloads: list[dict[str, Any]],
    responses: list[dict[str, Any]],
    by_id: dict[str, RecommendationCandidate],
) -> dict[str, Any]:
    summaries = [quality_summary(response, payload, by_id) for payload, response in zip(payloads, responses)]
    if not summaries:
        return {}
    keys = [
        "result_count",
        "duplicate_ids",
        "missing_from_index",
        "top10_distinct_channels",
        "top10_same_channel",
        "top10_genre_overlap",
    ]
    return {
        "cases": len(summaries),
        "all_current_excluded": all(not summary["current_returned"] for summary in summaries),
        "all_queue_excluded": all(not summary["queued_returned"] for summary in summaries),
        "averages": {
            key: round(statistics.mean(float(summary[key]) for summary in summaries), 3)
            for key in keys
        },
        "empty_result_cases": sum(1 for summary in summaries if summary["result_count"] == 0),
    }


def watch_payloads(candidates: list[RecommendationCandidate], user_id: str | None) -> list[dict[str, Any]]:
    non_movie = [
        candidate
        for candidate in candidates
        if candidate.content_kind != "movie" and not candidate.played
    ]
    if len(non_movie) < 12:
        non_movie = [candidate for candidate in candidates if candidate.content_kind != "movie"]
    selected = non_movie[:12]
    by_channel: dict[str, list[RecommendationCandidate]] = {}
    for candidate in candidates:
        if candidate.channel:
            by_channel.setdefault(candidate.channel, []).append(candidate)

    payloads: list[dict[str, Any]] = []
    for current in selected:
        same_channel = [
            candidate.item_id
            for candidate in by_channel.get(current.channel or "", [])
            if candidate.item_id != current.item_id
        ][:4]
        binge = None
        if current.channel and len(same_channel) >= 2:
            binge = {
                "channel": current.channel,
                "series_id": current.series_id,
                "streak_count": min(len(same_channel) + 1, 6),
            }
        payloads.append(
            {
                "algo": "blended",
                "user_id": user_id,
                "context": "watch",
                "limit": 28,
                "current_item_id": current.item_id,
                "queue_item_ids": same_channel[:2],
                "recent_item_ids": same_channel[2:4],
                "binge": binge,
            }
        )
    return payloads


def run_watch_cases(
    client: TestClient,
    payloads: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    durations: list[float] = []
    statuses: list[int] = []
    warnings: Counter[str] = Counter()
    responses: list[dict[str, Any]] = []
    for payload in payloads:
        start = time.perf_counter()
        response = client.post("/recommendations/indexed", json=payload)
        durations.append((time.perf_counter() - start) * 1000)
        statuses.append(response.status_code)
        data = response.json()
        responses.append(data)
        if data.get("warning"):
            warnings[str(data["warning"])] += 1
    return (
        {
            "label": "watch indexed sampled current items",
            "runs": len(payloads),
            "status_codes": sorted(set(statuses)),
            **summarize_durations(durations),
            "warnings": dict(warnings),
        },
        responses,
    )


def main() -> None:
    os.environ["ENABLE_LLM_RERANK"] = "false"
    settings = get_settings()
    if not settings.jellyfin_url:
        raise SystemExit("Set JELLYFIN_URL before running this benchmark.")
    if not (
        settings.jellyfin_api_key
        or (settings.jellyfin_username and settings.jellyfin_password)
    ):
        raise SystemExit("Set JELLYFIN_API_KEY or JELLYFIN_USERNAME/JELLYFIN_PASSWORD.")

    service = JellyfinIndexService(settings)
    refresh_start = time.perf_counter()
    user_index = service.refresh()
    refresh_ms = (time.perf_counter() - refresh_start) * 1000
    candidates = candidates_from_index(user_index)
    by_id = {candidate.item_id: candidate for candidate in candidates}
    user_id = user_index.get("user_id")
    client = TestClient(app)

    home_payload = {"algo": "blended", "user_id": user_id, "context": "home", "limit": 50}
    movie_payload = {"algo": "blended", "user_id": user_id, "context": "movie", "limit": 36}
    music_payload = {"algo": "blended", "user_id": user_id, "context": "music", "limit": 36}

    payloads = watch_payloads(candidates, user_id)
    watch_latency, watch_responses = run_watch_cases(client, payloads)

    content_kind_counts = Counter(candidate.content_kind or "unknown" for candidate in candidates)
    print(
        json.dumps(
            {
                "benchmark": "jellyGPT indexed recommendations on real Jellyfin data",
                "llm_rerank": "disabled",
                "index": {
                    "refresh_ms": round(refresh_ms, 3),
                    "user_id_present": bool(user_id),
                    "item_count": len(candidates),
                    "history_count": len(user_index.get("history", [])),
                    "content_kind_counts": dict(content_kind_counts),
                    "source_count": len(user_index.get("source_counts", {})),
                },
                "latency": [
                    time_endpoint(client, "home indexed", home_payload, 50),
                    time_endpoint(client, "movie indexed", movie_payload, 30),
                    time_endpoint(client, "music indexed", music_payload, 30),
                    watch_latency,
                ],
                "watch_quality": aggregate_watch_quality(payloads, watch_responses, by_id),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
