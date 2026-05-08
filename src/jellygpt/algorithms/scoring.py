from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone

from jellygpt.schemas import (
    BingeContext,
    PlaybackHistoryEvent,
    RecommendationCandidate,
    RecommendationItem,
    RecommendationRequest,
)

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
    context = (request.context or "").strip().lower()
    current_item = request.current_item
    excluded_item_ids = set(request.queue_item_ids or [])
    if current_item:
        excluded_item_ids.add(current_item.item_id)

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
        weight = _history_event_weight(event, now)
        for token in _tokens(event.item_name or ""):
            watched_tokens[token] += weight * 1.6

    ranked: list[RecommendationItem] = []
    for candidate in candidates:
        if not _is_candidate(candidate, excluded_item_ids):
            continue
        score, reasons = _score_candidate(
            candidate,
            algo,
            context,
            current_item,
            now,
            watched_channels,
            watched_tokens,
            watched_genres,
            watched_series,
            watched_parent_ids,
            set(request.recent_item_ids or []),
            request.binge,
        )
        ranked.append(
            RecommendationItem(
                item_id=candidate.item_id,
                score=round(score, 4),
                reason=reasons[0] if reasons else _fallback_reason(candidate),
            )
        )

    ranked.sort(key=lambda item: (-item.score, item.item_id))
    candidates_by_id = {candidate.item_id: candidate for candidate in candidates}
    return _diversify(ranked, candidates_by_id)[: request.limit]


def _score_candidate(
    candidate: RecommendationCandidate,
    algo: str,
    context: str,
    current_item: RecommendationCandidate | None,
    now: datetime,
    watched_channels: Counter[str],
    watched_tokens: Counter[str],
    watched_genres: Counter[str],
    watched_series: Counter[str],
    watched_parent_ids: Counter[str],
    recent_item_ids: set[str],
    binge: BingeContext | None,
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
        genre_multiplier = 4.0 if algo in {"label_profile", "blended", "llm_rerank"} else 1.5
        score += min(genre_hits * genre_multiplier, 18.0)
        reasons.append("similar genre")

    candidate_tokens = _title_tokens_without_channel(candidate)
    token_score = sum(min(watched_tokens[token], 8.0) for token in candidate_tokens)
    if token_score:
        if algo in {"label_profile", "blended", "llm_rerank"}:
            multiplier = 1.1
        elif algo == "existing_logic_like":
            multiplier = 0.75
        else:
            multiplier = 0.55
        score += min(token_score * multiplier, 30.0)
        reasons.append("matches watch history")

    if candidate.item_id in recent_item_ids or _recently_played(candidate, now):
        score -= 18.0
        reasons.append("recently played")

    profile_algos = {"label_profile", "blended", "llm_rerank"}
    if candidate.content_kind == "musicVideo" and algo in profile_algos:
        score += 3.0

    context_score, context_reasons = _current_context_score(candidate, current_item, context, algo)
    score += context_score
    reasons.extend(reason for reason in context_reasons if reason not in reasons)

    binge_score, binge_reasons = _binge_context_score(candidate, binge, context, algo)
    score += binge_score
    reasons.extend(reason for reason in binge_reasons if reason not in reasons)

    return score, reasons


def _is_candidate(candidate: RecommendationCandidate, excluded_item_ids: set[str]) -> bool:
    if candidate.item_id in excluded_item_ids:
        return False
    played_once = candidate.played and (candidate.play_count or 0) <= 1
    if played_once and candidate.content_kind != "musicVideo":
        return False
    if (candidate.playback_position_ticks or 0) > 0 and not candidate.played:
        return False
    return True


def _current_context_score(
    candidate: RecommendationCandidate,
    current_item: RecommendationCandidate | None,
    context: str,
    algo: str,
) -> tuple[float, list[str]]:
    if not current_item:
        return 0.0, []

    reasons: list[str] = []
    score = 0.0
    watch_weight = 1.0 if context == "watch" else 0.65
    profile_weight = 1.0 if algo in {"label_profile", "blended", "llm_rerank"} else 0.65
    weight = watch_weight * profile_weight

    current_kind = current_item.content_kind or current_item.type
    candidate_kind = candidate.content_kind or candidate.type
    if current_kind and candidate_kind:
        if current_kind == candidate_kind:
            score += 9.0 * watch_weight
        elif "movie" in {current_kind, candidate_kind}:
            score -= 18.0 * watch_weight
        else:
            score -= 4.0 * watch_weight

    current_channel = _norm(current_item.channel)
    candidate_channel = _norm(candidate.channel)
    if current_channel and current_channel == candidate_channel:
        score += 10.0 * watch_weight
        reasons.append("same channel")

    if current_item.series_id and current_item.series_id == candidate.series_id:
        score += 18.0 * watch_weight
        reasons.append("same series")
    if current_item.parent_id and current_item.parent_id == candidate.parent_id:
        score += 7.0 * watch_weight

    current_genres = _normalized_set(current_item.genres or [])
    candidate_genres = _normalized_set(candidate.genres or [])
    genre_overlap = len(current_genres.intersection(candidate_genres))
    if genre_overlap:
        score += min(genre_overlap * 12.0 * weight, 30.0)
        reasons.append("similar genre")

    current_title_tokens = _title_tokens_without_channel(current_item)
    candidate_title_tokens = _title_tokens_without_channel(candidate)
    title_overlap = len(current_title_tokens.intersection(candidate_title_tokens))
    if title_overlap:
        score += min(title_overlap * 9.0 * weight, 36.0)
        reasons.append("similar title")

    score += _duration_affinity(current_item, candidate) * watch_weight

    return score, reasons


def _binge_context_score(
    candidate: RecommendationCandidate,
    binge: BingeContext | None,
    context: str,
    algo: str,
) -> tuple[float, list[str]]:
    if not binge or binge.streak_count < 2:
        return 0.0, []

    reasons: list[str] = []
    score = 0.0
    streak_weight = min(max(float(binge.streak_count), 2.0), 8.0)
    watch_weight = 1.0 if context == "watch" else 0.5
    profile_weight = 1.0 if algo in {"label_profile", "blended", "llm_rerank"} else 0.6
    weight = watch_weight * profile_weight

    if binge.channel and _norm(binge.channel) == _norm(candidate.channel):
        score += min(streak_weight * 3.0 * weight, 18.0)
        reasons.append("continues current channel")
    if binge.series_id and binge.series_id == candidate.series_id:
        score += min(streak_weight * 4.0 * weight, 24.0)
        reasons.append("continues current series")

    return score, reasons


def _candidate_engagement(candidate: RecommendationCandidate) -> float:
    play_count = float(candidate.play_count or 0)
    if candidate.played:
        play_count = max(play_count, 1.0)
    if (candidate.playback_position_ticks or 0) > 0:
        play_count += 0.25
    return min(play_count, 6.0)


def _history_event_weight(event: PlaybackHistoryEvent, now: datetime) -> float:
    weight = max(float(event.total_count or 1), 1.0)
    if event.total_time:
        weight += min(float(event.total_time) / 3600.0, 8.0)

    latest = _parse_date(event.latest_date)
    if latest:
        age_days = max(0.0, (now - latest).total_seconds() / 86400.0)
        if age_days < 14:
            weight *= 1.35
        elif age_days < 90:
            weight *= 1.15
        elif age_days > 365:
            weight *= 0.75
    return weight


def _duration_affinity(
    current_item: RecommendationCandidate,
    candidate: RecommendationCandidate,
) -> float:
    if not current_item.run_time_ticks or not candidate.run_time_ticks:
        return 0.0
    current_duration = current_item.run_time_ticks
    candidate_duration = candidate.run_time_ticks
    ratio = min(current_duration, candidate_duration) / max(current_duration, candidate_duration)
    short_form_threshold = 8 * 60 * 10_000_000
    current_short = current_duration < short_form_threshold
    candidate_short = candidate_duration < short_form_threshold
    if current_short and candidate_short:
        return 8.0
    if current_short != candidate_short:
        return -8.0
    if ratio > 0.75:
        return 8.0
    if ratio > 0.5:
        return 4.0
    return 0.0


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


def _title_tokens_without_channel(candidate: RecommendationCandidate) -> set[str]:
    channel_tokens = set(_tokens(candidate.channel))
    return set(_tokens(candidate.title)) - channel_tokens


def _normalized_set(values: list[str]) -> set[str]:
    return {normalized for value in values if (normalized := _norm(value))}


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
        candidate = candidates_by_id.get(item.item_id)
        channel = _norm(candidate.channel if candidate else None)
        if channel and channel_counts[channel] >= max_per_channel:
            deferred.append(item)
            continue
        selected.append(item)
        if channel:
            channel_counts[channel] += 1
    return selected + deferred
