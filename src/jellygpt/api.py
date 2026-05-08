from datetime import datetime, timezone

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .algorithms.scoring import rank_candidates
from .config import get_settings
from .indexer import (
    IndexUnavailableError,
    JellyfinIndexService,
    candidates_from_index,
    current_item_from_index,
    filter_index_candidates,
    history_from_index,
)
from .schemas import (
    AlgorithmInfo,
    AlgorithmsResponse,
    HealthResponse,
    IndexedRecommendationRequest,
    IndexRefreshRequest,
    IndexStatusResponse,
    RecommendationRequest,
    RecommendationsResponse,
)

ALGORITHMS = [
    AlgorithmInfo(id="existing_logic_like", name="Existing JellyTube", available=True),
    AlgorithmInfo(id="recency_popularity", name="Recency / Popularity", available=True),
    AlgorithmInfo(id="label_profile", name="Label Profile", available=True),
    AlgorithmInfo(id="blended", name="Blended", available=True),
]


def create_app() -> FastAPI:
    app = FastAPI(title="jellyGPT", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(ok=True, version=__version__)

    @app.get("/algorithms", response_model=AlgorithmsResponse)
    def algorithms() -> AlgorithmsResponse:
        settings = get_settings()
        algos = list(ALGORITHMS)
        algos.append(
            AlgorithmInfo(
                id="llm_rerank",
                name="AI Rerank",
                available=settings.enable_llm_rerank,
                reason=None if settings.enable_llm_rerank else "Ollama reranking disabled",
            )
        )
        return AlgorithmsResponse(algorithms=algos)

    @app.get("/recommendations", response_model=RecommendationsResponse)
    def recommendations(
        algo: str = Query(default="blended"),
        user_id: str | None = Query(default=None),
        context: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> RecommendationsResponse:
        service = JellyfinIndexService(get_settings())
        request = IndexedRecommendationRequest(
            algo=algo,
            user_id=user_id,
            context=context,
            limit=limit,
        )
        user_index = service.load_user_index(user_id)
        if not user_index:
            return RecommendationsResponse(
                algo=algo,
                generated_at=None,
                cache_age_seconds=None,
                items=[],
                warning="No jellyGPT index is available yet; run POST /index/refresh.",
            )
        return _rank_indexed(user_index, request)

    @app.get("/index/status", response_model=IndexStatusResponse)
    def index_status(user_id: str | None = Query(default=None)) -> IndexStatusResponse:
        return JellyfinIndexService(get_settings()).status(user_id)

    @app.post("/index/refresh", response_model=IndexStatusResponse)
    def refresh_index(request: IndexRefreshRequest) -> IndexStatusResponse:
        service = JellyfinIndexService(get_settings())
        try:
            user_index = service.refresh(request.user_id)
        except IndexUnavailableError as exc:
            return IndexStatusResponse(
                available=False,
                user_id=request.user_id,
                warning=str(exc),
            )
        return service.status(user_index.get("user_id"))

    @app.post("/recommendations/indexed", response_model=RecommendationsResponse)
    def indexed_recommendations(request: IndexedRecommendationRequest) -> RecommendationsResponse:
        service = JellyfinIndexService(get_settings())
        try:
            user_index = service.get_or_refresh(request.user_id, refresh=request.refresh)
        except IndexUnavailableError as exc:
            return RecommendationsResponse(
                algo=request.algo,
                generated_at=None,
                cache_age_seconds=None,
                items=[],
                warning=str(exc),
            )
        return _rank_indexed(user_index, request)

    @app.post("/recommendations", response_model=RecommendationsResponse)
    def rank_recommendations(request: RecommendationRequest) -> RecommendationsResponse:
        limit = max(1, min(request.limit, 200))
        ranked = rank_candidates(request.model_copy(update={"limit": limit}))
        return RecommendationsResponse(
            algo=request.algo,
            generated_at=datetime.now(timezone.utc).isoformat(),
            cache_age_seconds=0,
            items=ranked,
            warning=None if ranked else "No eligible candidates to rank.",
        )

    return app


def _rank_indexed(
    user_index: dict,
    request: IndexedRecommendationRequest,
) -> RecommendationsResponse:
    limit = max(1, min(request.limit, 200))
    candidates = candidates_from_index(user_index)
    current_item = current_item_from_index(candidates, request)
    selected_candidates = filter_index_candidates(candidates, request, current_item)
    history = list(request.history or []) or history_from_index(user_index)
    rank_request = RecommendationRequest(
        algo=request.algo,
        user_id=request.user_id or user_index.get("user_id"),
        context=request.context,
        limit=limit,
        now=request.now,
        candidates=selected_candidates,
        current_item=current_item,
        history=history,
        recent_item_ids=request.recent_item_ids,
        queue_item_ids=request.queue_item_ids,
        binge=request.binge,
    )
    ranked = rank_candidates(rank_request)
    generated_at = datetime.now(timezone.utc).isoformat()
    cache_age = _index_age_seconds(user_index)
    warning = None
    if request.current_item_id and not current_item:
        warning = "Current item was not found in the jellyGPT index."
    if not ranked:
        warning = warning or "No eligible indexed candidates to rank."
    return RecommendationsResponse(
        algo=request.algo,
        generated_at=generated_at,
        cache_age_seconds=cache_age,
        items=ranked,
        warning=warning,
    )


def _index_age_seconds(user_index: dict) -> int | None:
    generated_at = user_index.get("generated_at")
    if not isinstance(generated_at, str):
        return None
    try:
        generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if not generated.tzinfo:
        generated = generated.replace(tzinfo=timezone.utc)
    return int((datetime.now(timezone.utc) - generated).total_seconds())


app = create_app()
