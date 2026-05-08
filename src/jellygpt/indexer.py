from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from . import __version__
from .config import Settings
from .schemas import (
    IndexedRecommendationRequest,
    IndexStatusResponse,
    PlaybackHistoryEvent,
    RecommendationCandidate,
)

INDEX_VERSION = 1
WATCH_INDEX_POOL_LIMIT = 1200
TOKEN_RE = re.compile(r"[a-z0-9]{3,}")
_CACHE_BY_PATH: dict[str, tuple[float, dict[str, Any]]] = {}
_CANDIDATES_BY_INDEX_KEY: dict[tuple[Any, ...], list[RecommendationCandidate]] = {}
_HISTORY_BY_INDEX_KEY: dict[tuple[Any, ...], list[PlaybackHistoryEvent]] = {}
ITEM_FIELDS = ",".join(
    [
        "Artists",
        "ArtistItems",
        "CommunityRating",
        "Container",
        "DateCreated",
        "Genres",
        "IndexNumber",
        "MediaSources",
        "OfficialRating",
        "Overview",
        "ParentId",
        "ParentIndexNumber",
        "PremiereDate",
        "ProductionYear",
        "RunTimeTicks",
        "SeasonId",
        "SeasonName",
        "SeriesId",
        "SeriesName",
        "Studios",
        "Tags",
        "UserData",
    ]
)


class IndexUnavailableError(RuntimeError):
    pass


class JellyfinIndexService:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def path(self) -> Path:
        if self.settings.index_path:
            return Path(self.settings.index_path)
        return Path(self.settings.cache_dir) / "jellygpt-index.json"

    def status(self, user_id: str | None = None) -> IndexStatusResponse:
        user_index = self.load_user_index(user_id)
        if not user_index:
            return IndexStatusResponse(
                available=False,
                user_id=user_id,
                warning="No jellyGPT index is available yet; run POST /index/refresh.",
            )
        return _status_from_user_index(user_index)

    def load_user_index(self, user_id: str | None = None) -> dict[str, Any] | None:
        cache = self._read_cache()
        users = cache.get("users", {})
        if not isinstance(users, dict) or not users:
            return None
        valid_users = [value for value in users.values() if isinstance(value, dict)]
        if user_id:
            value = users.get(user_id)
            if isinstance(value, dict):
                return value
            normalized_user_id = _normalize_db_id(user_id)
            for key, candidate in users.items():
                if _normalize_db_id(key) == normalized_user_id and isinstance(candidate, dict):
                    return candidate
            for candidate in valid_users:
                if _normalize_db_id(candidate.get("user_id")) == normalized_user_id:
                    return candidate
            return None
        if len(valid_users) == 1:
            return valid_users[0]
        return max(valid_users, key=lambda value: _parse_date(value.get("generated_at")) or datetime.min.replace(tzinfo=timezone.utc))

    def get_or_refresh(
        self,
        user_id: str | None = None,
        *,
        refresh: bool = False,
    ) -> dict[str, Any]:
        user_index = self.load_user_index(user_id)
        stale = user_index is None or self._cache_age_seconds(user_index) > self.settings.index_max_age_seconds
        if not refresh and user_index and not stale:
            return user_index
        try:
            return self.refresh(user_id)
        except IndexUnavailableError:
            if user_index:
                return user_index
            raise

    def refresh(self, user_id: str | None = None) -> dict[str, Any]:
        if not self.settings.jellyfin_url:
            return self._refresh_from_local_databases(user_id)

        base_url = self.settings.jellyfin_url.rstrip("/")
        auth = self._authenticate(base_url, user_id)
        effective_user_id = user_id or auth["user_id"]
        if not effective_user_id:
            raise IndexUnavailableError("No Jellyfin user id is available for indexing.")

        headers = _jellyfin_headers(auth["token"])
        items_by_id: dict[str, RecommendationCandidate] = {}
        source_counts: dict[str, int] = {}

        with httpx.Client(base_url=base_url, headers=headers, timeout=45.0) as client:
            views = self._get_views(client, effective_user_id)
            for view in views:
                source_items = self._fetch_items_for_source(client, effective_user_id, view)
                source_count = 0
                for raw_item in source_items:
                    candidate = _candidate_from_item(raw_item, view)
                    if not candidate:
                        continue
                    items_by_id[candidate.item_id] = candidate
                    source_count += 1
                if source_count:
                    source_counts[_source_key(view)] = source_count
            history = self._fetch_history(client)

        generated_at = datetime.now(timezone.utc).isoformat()
        user_index = {
            "user_id": effective_user_id,
            "generated_at": generated_at,
            "server_url": base_url,
            "items": [
                item.model_dump()
                for item in sorted(items_by_id.values(), key=lambda candidate: candidate.item_id)
            ],
            "history": [event.model_dump() for event in history],
            "source_counts": source_counts,
        }
        cache = self._read_cache()
        cache["version"] = INDEX_VERSION
        users = cache.setdefault("users", {})
        if not isinstance(users, dict):
            users = {}
            cache["users"] = users
        users[effective_user_id] = user_index
        self._write_cache(cache)
        return user_index

    def _fetch_items_for_source(
        self,
        client: httpx.Client,
        user_id: str,
        view: dict[str, Any],
    ) -> list[dict[str, Any]]:
        limit = max(1, self.settings.index_limit_per_source)
        page_size = min(250, limit)
        seen: dict[str, dict[str, Any]] = {}
        sort_orders = [
            ("DateCreated", "Descending"),
            ("PremiereDate", "Descending"),
            ("DatePlayed", "Descending"),
            ("SortName", "Ascending"),
        ]

        for sort_by, sort_order in sort_orders:
            start_index = 0
            while len(seen) < limit:
                params = {
                    "ParentId": view["Id"],
                    "Recursive": "true",
                    "IncludeItemTypes": _item_types_for_collection(view.get("CollectionType")),
                    "Fields": ITEM_FIELDS,
                    "EnableUserData": "true",
                    "ImageTypeLimit": "0",
                    "Limit": str(min(page_size, limit - len(seen))),
                    "StartIndex": str(start_index),
                    "SortBy": sort_by,
                    "SortOrder": sort_order,
                }
                try:
                    response = client.get(f"/Users/{user_id}/Items", params=params)
                    response.raise_for_status()
                except httpx.HTTPError:
                    break
                payload = response.json()
                items = payload.get("Items", [])
                if not isinstance(items, list) or not items:
                    break
                for item in items:
                    item_id = item.get("Id")
                    if item_id:
                        seen[item_id] = item
                start_index += len(items)
                total = int(payload.get("TotalRecordCount") or 0)
                if start_index >= total:
                    break
            if len(seen) >= limit:
                break

        return list(seen.values())

    def _authenticate(self, base_url: str, requested_user_id: str | None) -> dict[str, str]:
        if self.settings.jellyfin_username and self.settings.jellyfin_password:
            with httpx.Client(base_url=base_url, headers=_jellyfin_headers(), timeout=30.0) as client:
                response = client.post(
                    "/Users/AuthenticateByName",
                    json={
                        "Username": self.settings.jellyfin_username,
                        "Pw": self.settings.jellyfin_password,
                    },
                )
                try:
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    raise IndexUnavailableError("Jellyfin username/password authentication failed.") from exc
                payload = response.json()
            token = payload.get("AccessToken")
            user = payload.get("User") or {}
            user_id = requested_user_id or user.get("Id")
            if token and user_id:
                return {"token": token, "user_id": user_id}
            raise IndexUnavailableError("Jellyfin authentication response did not include a token/user.")

        if self.settings.jellyfin_api_key:
            if requested_user_id:
                return {"token": self.settings.jellyfin_api_key, "user_id": requested_user_id}
            with httpx.Client(
                base_url=base_url,
                headers=_jellyfin_headers(self.settings.jellyfin_api_key),
                timeout=30.0,
            ) as client:
                try:
                    response = client.get("/Users")
                    response.raise_for_status()
                    users = response.json()
                except httpx.HTTPError as exc:
                    raise IndexUnavailableError("Jellyfin API key could not list users.") from exc
            if isinstance(users, list) and users:
                first_user_id = users[0].get("Id")
                if first_user_id:
                    return {"token": self.settings.jellyfin_api_key, "user_id": first_user_id}
            raise IndexUnavailableError("JELLYFIN_USER_ID is required when no user can be inferred.")

        raise IndexUnavailableError("Configure JELLYFIN_API_KEY or JELLYFIN_USERNAME/JELLYFIN_PASSWORD.")

    def _refresh_from_local_databases(self, user_id: str | None = None) -> dict[str, Any]:
        jellyfin_db = Path(self.settings.jellyfin_db)
        playback_db = Path(self.settings.playback_db)
        if not jellyfin_db.exists():
            raise IndexUnavailableError(
                "JELLYFIN_URL is not configured and local JELLYFIN_DB is unavailable."
            )

        effective_user_id = user_id or self._first_local_user_id(jellyfin_db)
        items_by_id: dict[str, RecommendationCandidate] = {}
        source_counts: dict[str, int] = {}

        with sqlite3.connect(f"file:{jellyfin_db}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            user_data = self._local_user_data(conn, effective_user_id)
            parents = self._local_parent_names(conn)
            for row in conn.execute(
                """
                SELECT Id, Name, Type, MediaType, IsMovie, ParentId, SeriesId, SeriesName,
                       Genres, DateCreated, PremiereDate, RunTimeTicks, AlbumArtists,
                       Artists, Studios
                FROM BaseItems
                WHERE MediaType = 'Video'
                  AND Name IS NOT NULL
                  AND IsVirtualItem = 0
                """
            ):
                candidate = _candidate_from_db_row(row, user_data.get(_normalize_db_id(row["Id"])), parents)
                if not candidate:
                    continue
                items_by_id[candidate.item_id] = candidate
                source_counts[candidate.content_kind or "video"] = source_counts.get(candidate.content_kind or "video", 0) + 1

        history = self._local_history(playback_db, effective_user_id)
        generated_at = datetime.now(timezone.utc).isoformat()
        user_index = {
            "user_id": effective_user_id,
            "generated_at": generated_at,
            "server_url": "local-db",
            "items": [
                item.model_dump()
                for item in sorted(items_by_id.values(), key=lambda candidate: candidate.item_id)
            ],
            "history": [event.model_dump() for event in history],
            "source_counts": source_counts,
        }
        cache = self._read_cache()
        cache["version"] = INDEX_VERSION
        users = cache.setdefault("users", {})
        if not isinstance(users, dict):
            users = {}
            cache["users"] = users
        users[effective_user_id] = user_index
        self._write_cache(cache)
        return user_index

    def _first_local_user_id(self, jellyfin_db: Path) -> str | None:
        with sqlite3.connect(f"file:{jellyfin_db}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT Id FROM Users ORDER BY LastActivityDate DESC NULLS LAST LIMIT 1"
            ).fetchone()
            return str(row["Id"]) if row and row["Id"] else None

    def _local_user_data(
        self,
        conn: sqlite3.Connection,
        user_id: str | None,
    ) -> dict[str, sqlite3.Row]:
        if not user_id:
            return {}
        rows = conn.execute(
            """
            SELECT ItemId, LastPlayedDate, PlayCount, Played, PlaybackPositionTicks
            FROM UserData
            WHERE UserId = ?
            """,
            (user_id,),
        )
        return {_normalize_db_id(row["ItemId"]): row for row in rows}

    def _local_parent_names(self, conn: sqlite3.Connection) -> dict[str, str]:
        rows = conn.execute(
            "SELECT Id, Name FROM BaseItems WHERE Name IS NOT NULL AND IsFolder = 1"
        )
        return {_normalize_db_id(row["Id"]): row["Name"] for row in rows}

    def _local_history(self, playback_db: Path, user_id: str | None) -> list[PlaybackHistoryEvent]:
        if not playback_db.exists():
            return []
        query = """
            SELECT ItemName, COUNT(*) AS TotalCount, SUM(PlayDuration) AS TotalTime,
                   MAX(DateCreated) AS LatestDate
            FROM PlaybackActivity
            WHERE ItemName IS NOT NULL
        """
        params: list[Any] = []
        if user_id:
            query += " AND (lower(replace(UserId, '-', '')) = ? OR UserId IS NULL OR UserId = '')"
            params.append(_normalize_db_id(user_id))
        query += " GROUP BY ItemName ORDER BY LatestDate DESC LIMIT 2000"
        with sqlite3.connect(f"file:{playback_db}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            return [
                PlaybackHistoryEvent(
                    item_name=row["ItemName"],
                    total_count=row["TotalCount"],
                    total_time=row["TotalTime"],
                    latest_date=row["LatestDate"],
                )
                for row in conn.execute(query, params)
            ]

    def _get_views(self, client: httpx.Client, user_id: str) -> list[dict[str, Any]]:
        response = client.get(f"/Users/{user_id}/Views")
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise IndexUnavailableError("Jellyfin library views could not be loaded.") from exc
        views = response.json().get("Items", [])
        if not isinstance(views, list):
            return []
        return [view for view in views if _content_kind_for_collection(view.get("CollectionType"))]

    def _fetch_history(self, client: httpx.Client) -> list[PlaybackHistoryEvent]:
        try:
            response = client.get(
                "/user_usage_stats/user_activity",
                params={
                    "days": str(max(1, self.settings.index_history_days)),
                    "timezoneOffset": "0",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return []
        payload = response.json()
        if not isinstance(payload, list):
            return []
        events: list[PlaybackHistoryEvent] = []
        for row in payload[:2000]:
            if not isinstance(row, dict):
                continue
            events.append(
                PlaybackHistoryEvent(
                    item_name=_first_value(row, "item_name", "ItemName", "Name"),
                    total_count=_first_value(row, "total_count", "TotalCount"),
                    total_time=_first_value(row, "total_time", "TotalTime"),
                    latest_date=_first_value(row, "latest_date", "LatestDate"),
                )
            )
        return events

    def _read_cache(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": INDEX_VERSION, "users": {}}
        cache_key = str(self.path)
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return {"version": INDEX_VERSION, "users": {}}
        cached = _CACHE_BY_PATH.get(cache_key)
        if cached and cached[0] == mtime:
            return cached[1]
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": INDEX_VERSION, "users": {}}
        if not isinstance(payload, dict):
            return {"version": INDEX_VERSION, "users": {}}
        _CACHE_BY_PATH[cache_key] = (mtime, payload)
        return payload

    def _write_cache(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(self.path)
        try:
            _CACHE_BY_PATH[str(self.path)] = (self.path.stat().st_mtime, payload)
        except OSError:
            pass

    def _cache_age_seconds(self, user_index: dict[str, Any]) -> int:
        generated_at = _parse_date(user_index.get("generated_at"))
        if not generated_at:
            return self.settings.index_max_age_seconds + 1
        return int((datetime.now(timezone.utc) - generated_at).total_seconds())


def candidates_from_index(user_index: dict[str, Any]) -> list[RecommendationCandidate]:
    index_key = _index_key(user_index)
    cached = _CANDIDATES_BY_INDEX_KEY.get(index_key)
    if cached is not None:
        return cached

    candidates: list[RecommendationCandidate] = []
    for raw in user_index.get("items", []):
        if not isinstance(raw, dict):
            continue
        try:
            candidates.append(RecommendationCandidate.model_validate(raw))
        except ValueError:
            continue
    _CANDIDATES_BY_INDEX_KEY[index_key] = candidates
    return candidates


def history_from_index(user_index: dict[str, Any]) -> list[PlaybackHistoryEvent]:
    index_key = _index_key(user_index)
    cached = _HISTORY_BY_INDEX_KEY.get(index_key)
    if cached is not None:
        return cached

    history: list[PlaybackHistoryEvent] = []
    for raw in user_index.get("history", []):
        if not isinstance(raw, dict):
            continue
        try:
            history.append(PlaybackHistoryEvent.model_validate(raw))
        except ValueError:
            continue
    _HISTORY_BY_INDEX_KEY[index_key] = history
    return history


def current_item_from_index(
    candidates: Iterable[RecommendationCandidate],
    request: IndexedRecommendationRequest,
) -> RecommendationCandidate | None:
    if request.current_item:
        return request.current_item
    if not request.current_item_id:
        return None
    return next(
        (candidate for candidate in candidates if candidate.item_id == request.current_item_id),
        None,
    )


def filter_index_candidates(
    candidates: list[RecommendationCandidate],
    request: IndexedRecommendationRequest,
    current_item: RecommendationCandidate | None,
) -> list[RecommendationCandidate]:
    context = (request.context or "").strip().lower()
    if context == "movie":
        return [candidate for candidate in candidates if candidate.content_kind == "movie"]
    if context == "music":
        return [candidate for candidate in candidates if candidate.content_kind == "musicVideo"]
    if context == "home":
        return [candidate for candidate in candidates if candidate.content_kind != "movie"]
    if context == "watch" and current_item:
        current_kind = current_item.content_kind or current_item.type
        if current_kind == "movie":
            return [candidate for candidate in candidates if candidate.content_kind == "movie"]
        return _watch_candidate_slice(
            [candidate for candidate in candidates if candidate.content_kind != "movie"],
            current_item,
            request,
        )
    return candidates


def _status_from_user_index(user_index: dict[str, Any]) -> IndexStatusResponse:
    generated_at = user_index.get("generated_at")
    generated_dt = _parse_date(generated_at)
    age = None
    if generated_dt:
        age = int((datetime.now(timezone.utc) - generated_dt).total_seconds())
    items = user_index.get("items", [])
    history = user_index.get("history", [])
    return IndexStatusResponse(
        available=True,
        generated_at=generated_at if isinstance(generated_at, str) else None,
        cache_age_seconds=age,
        user_id=user_index.get("user_id"),
        item_count=len(items) if isinstance(items, list) else 0,
        history_count=len(history) if isinstance(history, list) else 0,
        source_counts=user_index.get("source_counts", {}),
        warning=None,
    )


def _index_key(user_index: dict[str, Any]) -> tuple[Any, ...]:
    items = user_index.get("items", [])
    history = user_index.get("history", [])
    return (
        user_index.get("user_id"),
        user_index.get("generated_at"),
        len(items) if isinstance(items, list) else 0,
        len(history) if isinstance(history, list) else 0,
    )


def _watch_candidate_slice(
    candidates: list[RecommendationCandidate],
    current_item: RecommendationCandidate,
    request: IndexedRecommendationRequest,
) -> list[RecommendationCandidate]:
    if len(candidates) <= WATCH_INDEX_POOL_LIMIT:
        return candidates

    now = datetime.now(timezone.utc)
    current_channel = _normalized_text(current_item.channel)
    current_genres = {_normalized_text(genre) for genre in current_item.genres or []}
    current_genres.discard("")
    current_tokens = set(_text_tokens(current_item.title))
    binge_channel = _normalized_text(request.binge.channel if request.binge else None)
    binge_series = request.binge.series_id if request.binge else None
    excluded = set(request.queue_item_ids or [])
    if request.current_item_id:
        excluded.add(request.current_item_id)
    excluded.add(current_item.item_id)

    scored: list[tuple[float, str, RecommendationCandidate]] = []
    for candidate in candidates:
        score = 0.0
        channel = _normalized_text(candidate.channel)
        if candidate.item_id in excluded:
            score -= 500.0
        if current_item.series_id and candidate.series_id == current_item.series_id:
            score += 120.0
        if current_item.parent_id and candidate.parent_id == current_item.parent_id:
            score += 40.0
        if current_channel and channel == current_channel:
            score += 80.0
        if binge_series and candidate.series_id == binge_series:
            score += 70.0
        if binge_channel and channel == binge_channel:
            score += 55.0
        candidate_genres = {_normalized_text(genre) for genre in candidate.genres or []}
        candidate_genres.discard("")
        score += len(current_genres.intersection(candidate_genres)) * 35.0
        score += len(current_tokens.intersection(_text_tokens(candidate.title))) * 22.0
        if not candidate.played:
            score += 8.0
        score += _recency_slice_score(candidate, now)
        scored.append((score, candidate.item_id, candidate))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [candidate for _, _, candidate in scored[:WATCH_INDEX_POOL_LIMIT]]


def _recency_slice_score(candidate: RecommendationCandidate, now: datetime) -> float:
    item_date = _parse_date(candidate.premiere_date) or _parse_date(candidate.date_created)
    if not item_date:
        return 0.0
    age_days = max(0.0, (now - item_date).total_seconds() / 86400.0)
    return max(0.0, 24.0 - min(age_days, 720.0) / 30.0)


def _text_tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return {token for token in TOKEN_RE.findall(value.lower()) if not token.isdigit()}


def _normalized_text(value: str | None) -> str:
    return " ".join(sorted(_text_tokens(value)))


def _candidate_from_db_row(
    row: sqlite3.Row,
    user_data: sqlite3.Row | None,
    parents: dict[str, str],
) -> RecommendationCandidate | None:
    item_id = _normalize_db_id(row["Id"])
    title = row["Name"]
    if not item_id or not title:
        return None
    content_kind = _content_kind_for_db_row(row)
    return RecommendationCandidate(
        item_id=item_id,
        title=title,
        type=_short_type(row["Type"]),
        content_kind=content_kind,
        channel=_channel_name_from_db_row(row, parents, content_kind),
        series_id=_normalize_db_id(row["SeriesId"]),
        parent_id=_normalize_db_id(row["ParentId"]),
        genres=_split_db_list(row["Genres"]),
        date_created=row["DateCreated"],
        premiere_date=row["PremiereDate"],
        last_played_date=user_data["LastPlayedDate"] if user_data else None,
        run_time_ticks=row["RunTimeTicks"],
        play_count=user_data["PlayCount"] if user_data else None,
        played=bool(user_data["Played"]) if user_data else None,
        playback_position_ticks=user_data["PlaybackPositionTicks"] if user_data else None,
    )


def _candidate_from_item(
    item: dict[str, Any],
    view: dict[str, Any],
) -> RecommendationCandidate | None:
    item_id = item.get("Id")
    title = item.get("Name")
    if not item_id or not title:
        return None
    user_data = item.get("UserData") or {}
    collection_type = view.get("CollectionType")
    content_kind = _content_kind_for_collection(collection_type) or _content_kind_for_item(item)
    return RecommendationCandidate(
        item_id=item_id,
        title=title,
        type=item.get("Type"),
        content_kind=content_kind,
        channel=_channel_name(item, view),
        series_id=item.get("SeriesId"),
        parent_id=item.get("ParentId"),
        genres=item.get("Genres") or [],
        date_created=item.get("DateCreated"),
        premiere_date=item.get("PremiereDate"),
        last_played_date=user_data.get("LastPlayedDate"),
        run_time_ticks=item.get("RunTimeTicks"),
        play_count=user_data.get("PlayCount"),
        played=user_data.get("Played"),
        playback_position_ticks=user_data.get("PlaybackPositionTicks"),
    )


def _channel_name(item: dict[str, Any], view: dict[str, Any]) -> str | None:
    content_kind = _content_kind_for_collection(view.get("CollectionType")) or _content_kind_for_item(item)
    if content_kind == "movie":
        return view.get("Name") or "Jellyfin Movies"
    if item.get("SeriesName"):
        return item["SeriesName"]
    artist_items = item.get("ArtistItems") or []
    if artist_items and artist_items[0].get("Name"):
        return artist_items[0]["Name"]
    artists = item.get("Artists") or []
    if artists:
        return artists[0]
    studios = item.get("Studios") or []
    if studios and studios[0].get("Name"):
        return studios[0]["Name"]
    return _title_channel(item.get("Name"), content_kind)


def _title_channel(title: str | None, content_kind: str | None) -> str | None:
    if not title:
        return None
    clean_title = title.rsplit("[", 1)[0].strip()
    if content_kind == "musicVideo":
        for separator in [" - ", " - ", ": "]:
            if separator in clean_title:
                return clean_title.split(separator, 1)[0].strip()
    for separator in [" | ", " - ", " - ", " -- "]:
        if separator in clean_title:
            value = clean_title.rsplit(separator, 1)[-1].strip()
            if value:
                return value
    return None


def _content_kind_for_collection(collection_type: str | None) -> str | None:
    if collection_type in {"tvshows", "homevideos"}:
        return "video"
    if collection_type == "movies":
        return "movie"
    if collection_type == "musicvideos":
        return "musicVideo"
    return None


def _content_kind_for_item(item: dict[str, Any]) -> str:
    item_type = item.get("Type")
    if item_type == "Movie":
        return "movie"
    if item_type == "MusicVideo":
        return "musicVideo"
    return "video"


def _content_kind_for_db_row(row: sqlite3.Row) -> str:
    item_type = str(row["Type"] or "")
    name = str(row["Name"] or "")
    parent = str(row["ParentId"] or "")
    if row["IsMovie"]:
        return "movie"
    if "MusicVideo" in item_type:
        return "musicVideo"
    if "movie" in parent.lower() or "/movies/" in name.lower():
        return "movie"
    return "video"


def _item_types_for_collection(collection_type: str | None) -> str:
    if collection_type == "movies":
        return "Movie"
    if collection_type == "musicvideos":
        return "MusicVideo"
    return "Video,Episode"


def _source_key(view: dict[str, Any]) -> str:
    collection_type = view.get("CollectionType") or "unknown"
    name = view.get("Name") or "library"
    return f"{_content_kind_for_collection(collection_type) or 'media'}:{name}"


def _jellyfin_headers(token: str | None = None) -> dict[str, str]:
    authorization = (
        'MediaBrowser Client="jellyGPT", Device="jellyGPT", '
        f'DeviceId="jellygpt-sidecar", Version="{__version__}"'
    )
    if token:
        authorization = f"{authorization}, Token={token}"
    headers = {"X-Emby-Authorization": authorization}
    if token:
        headers["X-Emby-Token"] = token
    return headers


def _first_value(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def _normalize_db_id(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("-", "").lower()


def _short_type(value: Any) -> str | None:
    if not value:
        return None
    return str(value).rsplit(".", 1)[-1]


def _split_db_list(value: Any) -> list[str]:
    if not value:
        return []
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    for separator in ["|", ";", ","]:
        if separator in text:
            return [part.strip() for part in text.split(separator) if part.strip()]
    return [text]


def _channel_name_from_db_row(
    row: sqlite3.Row,
    parents: dict[str, str],
    content_kind: str | None,
) -> str | None:
    if row["SeriesName"]:
        return row["SeriesName"]
    artists = _split_db_list(row["AlbumArtists"]) or _split_db_list(row["Artists"])
    if artists:
        return artists[0]
    studios = _split_db_list(row["Studios"])
    if studios:
        return studios[0]
    parent_name = parents.get(_normalize_db_id(row["ParentId"]))
    if parent_name:
        return parent_name
    return _title_channel(row["Name"], content_kind)


def _parse_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
