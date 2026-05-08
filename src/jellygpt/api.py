from datetime import datetime, timezone

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .algorithms.scoring import rank_candidates
from .config import get_settings
from .schemas import (
    AlgorithmInfo,
    AlgorithmsResponse,
    HealthResponse,
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
        limit: int = Query(default=50, ge=1, le=200),
    ) -> RecommendationsResponse:
        # Legacy/cache-read endpoint. The active JellyTube integration uses the
        # POST form below so the sidecar can rank the already-loaded Jellyfin
        # library without receiving Jellyfin credentials.
        return RecommendationsResponse(
            algo=algo,
            generated_at=None,
            cache_age_seconds=None,
            items=[],
            warning="No cache reader implemented yet; use POST /recommendations with candidates.",
        )

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


app = create_app()
