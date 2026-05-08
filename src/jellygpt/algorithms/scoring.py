from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone

from jellygpt.schemas import RecommendationCandidate, RecommendationRequest, RecommendationItem

TOKEN_RE = re.compile(r"[a-z0-9]{3,}")

STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "official",
    "video",
    "episode",
    "part",
    "full",
    "live",
}


def rank_candidates(request: RecommendationRequest) -> list[RecommendationItem]:
    algo = request.algo or "blended"
    candidates = [candidate for candidate in request.candidates if candidate.item_id]
    history = list(request.history or [])
    now = _parse_date(request.now) or datetime.now(timezone.utc)

    watched_channels = Counter[str]()
    watched_tokens = Counter[str]()
    watched_genres = Counter[str]()
    watched_series = Counter[str]()
    watched_parent_ids = Counter[str]()

    for candidate in candidates:
        engagement = _candidate_engagement(candidate)
        if engagement <= 0:
            continue
        watched_channels[_norm(candidate.channel)] += engagement
        if candidate.series_id:
            watched_series[candidate.series_id] += engagement
        if candidate.parent_id:
            watched_parent_ids[candidate.parent_id] += engagement
        for genre in candidate.genres or []:
            watched_genres[_norm(genre)] += engagement
        for token in _tokens(candidate.title, candidate.channel, *(candidate.genres or [])):
            watched_tokens[token] += engagement

    for event in history:
        weight = max(float(event.total_count or 1), 1.0)
        if event.total_time:
            weight += min(float(event.total_time) / 3600.0, 8.0)
        for token in _tokens(event.item_name or ""):
            watched_tokens[token] += weight * 1.6

    ranked: list[RecommendationItem] = []
    for candidate in candidates:
        if not _is_candidate(candidate):
            continue
        score, reasons = _score_candidate(
            candidate,
            algo,
            now,
            watched_channels,
            watched_tokens,
            watched_genres,
            watched_series,
            watched_parent_ids,
            set(request.recent_item_ids or []),
        )
        ranked.append(
            RecommendationItem(
                item_id=candidate.item_id,
                score=round(score, 4),
                reason=reasons[0] if reasons else _fallback_reason(candidate),
            )
        )

    ranked.sort(key=lambda item: (-item.score, item.item_id))
    return _diversify(ranked, {candidate.item_id: candidate for candidate in candidates})[: request.limit]


def _score_candidate(
    candidate: RecommendationCandidate,
    algo: str,
    now: datetime,
    watched_channels: Counter[str],
    watched_tokens: Counter[str],
    watched_genres: Counter[str],
    watched_series: Counter[str],
    watched_parent_ids: Counter[str],
    recent_item_ids: set[str],
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    age_days = _age_days(candidate, now)
    played = candidate.played or (candidate.play_count or 0) > 0

    if algo == "existing_logic_like":
        score += 6 if played else 20
        if age_days < 14:
            score += 12
            reasons.append("new")
        elif age_days < 60:
            score += 6
    elif algo == "recency_popularity":
        score += max(0.0, 30.0 - min(age_days, 365.0) / 12.0)
        score += min(float(candidate.play_count or 0) * 3.0, 18.0)
        if age_days < 21:
            reasons.append("recent")
    elif algo == "label_profile":
        score += 8 if not played else 2
    else:  # blended and llm_rerank fallback path
        score += 14 if not played else 5
        score += max(0.0, 14.0 - min(age_days, 180.0) / 18.0)

    channel = _norm(candidate.channel)
    if channel and watched_channels[channel]:
        bump = min(watched_channels[channel] * (3.0 if algo != "recency_popularity" else 1.5), 24.0)
        score += bump
        reasons.append("from channels you watch")

    if candidate.series_id and watched_series[candidate.series_id]:
        score += min(watched_series[candidate.series_id] * 4.0, 22.0)
        reasons.append("same series")
    if candidate.parent_id and watched_parent_ids[candidate.parent_id]:
        score += min(watched_parent_ids[candidate.parent_id] * 2.0, 10.0)

    genre_hits = sum(watched_genres[_norm(genre)] for genre in candidate.genres or [])
    if genre_hits:
        score += min(genre_hits * (4.0 if algo in {"label_profile", "blended", "llm_rerank"} else 1.5), 18.0)
        reasons.append("similar genre")

    token_score = sum(min(watched_tokens[token], 8.0) for token in _tokens(candidate.title, candidate.channel))
    if token_score:
        multiplier = 1.1 if algo in {"label_profile", "blended", "llm_rerank"} else 0.45
        score += min(token_score * multiplier, 30.0)
        reasons.append("matches watch history")

    if candidate.item_id in recent_item_ids or _recently_played(candidate, now):
        score -= 18.0
        reasons.append("recently played")

    if candidate.content_kind == "musicVideo" and algo in {"label_profile", "blended", "llm_rerank"}:
        score += 3.0

    return score, reasons


def _is_candidate(candidate: RecommendationCandidate) -> bool:
    if candidate.played and (candidate.play_count or 0) <= 1 and candidate.content_kind != "musicVideo":
        return False
    if (candidate.playback_position_ticks or 0) > 0 and not candidate.played:
        return False
    return True


def _candidate_engagement(candidate: RecommendationCandidate) -> float:
    play_count = float(candidate.play_count or 0)
    if candidate.played:
        play_count = max(play_count, 1.0)
    if (candidate.playback_position_ticks or 0) > 0:
        play_count += 0.25
    return min(play_count, 6.0)


def _age_days(candidate: RecommendationCandidate, now: datetime) -> float:
    item_date = _parse_date(candidate.premiere_date) or _parse_date(candidate.date_created)
    if not item_date:
        return 365.0
    return max(0.0, (now - item_date).total_seconds() / 86400.0)


def _recently_played(candidate: RecommendationCandidate, now: datetime) -> bool:
    last_played = _parse_date(candidate.last_played_date)
    if not last_played:
        return False
    return (now - last_played).total_seconds() < 3 * 86400


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _tokens(*parts: str | None) -> list[str]:
    tokens: list[str] = []
    for part in parts:
        if not part:
            continue
        for token in TOKEN_RE.findall(part.lower()):
            if token not in STOP_WORDS and not token.isdigit():
                tokens.append(token)
    return tokens


def _norm(value: str | None) -> str:
    return " ".join(_tokens(value or ""))


def _fallback_reason(candidate: RecommendationCandidate) -> str:
    if candidate.channel:
        return f"From {candidate.channel}"
    return "Recommended by jellyGPT"


def _diversify(
    ranked: list[RecommendationItem],
    candidates_by_id: dict[str, RecommendationCandidate],
    max_per_channel: int = 6,
) -> list[RecommendationItem]:
    selected: list[RecommendationItem] = []
    deferred: list[RecommendationItem] = []
    channel_counts = Counter[str]()
    for item in ranked:
        channel = _norm(candidates_by_id.get(item.item_id).channel if candidates_by_id.get(item.item_id) else None)
        if channel and channel_counts[channel] >= max_per_channel:
            deferred.append(item)
            continue
        selected.append(item)
        if channel:
            channel_counts[channel] += 1
    return selected + deferred
