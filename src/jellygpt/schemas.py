from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    ok: bool
    version: str


class AlgorithmInfo(BaseModel):
    id: str
    name: str
    available: bool
    reason: str | None = None


class AlgorithmsResponse(BaseModel):
    algorithms: list[AlgorithmInfo]


class PlaybackHistoryEvent(BaseModel):
    item_name: str | None = None
    total_count: int | None = None
    total_time: int | float | None = None
    latest_date: str | None = None


class RecommendationCandidate(BaseModel):
    item_id: str
    title: str
    type: str | None = None
    content_kind: str | None = None
    channel: str | None = None
    series_id: str | None = None
    parent_id: str | None = None
    genres: list[str] = Field(default_factory=list)
    date_created: str | None = None
    premiere_date: str | None = None
    last_played_date: str | None = None
    run_time_ticks: int | None = None
    play_count: int | None = None
    played: bool | None = None
    playback_position_ticks: int | None = None


class RecommendationRequest(BaseModel):
    algo: str = "blended"
    user_id: str | None = None
    context: str | None = None
    limit: int = 50
    now: str | None = None
    candidates: list[RecommendationCandidate]
    current_item: RecommendationCandidate | None = None
    history: list[PlaybackHistoryEvent] = Field(default_factory=list)
    recent_item_ids: list[str] = Field(default_factory=list)
    queue_item_ids: list[str] = Field(default_factory=list)


class RecommendationItem(BaseModel):
    item_id: str
    score: float
    reason: str | None = None


class RecommendationsResponse(BaseModel):
    algo: str
    generated_at: str | None
    cache_age_seconds: int | None
    items: list[RecommendationItem]
    warning: str | None = None
