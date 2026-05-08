import os

from pydantic import BaseModel


class Settings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8787
    jellyfin_url: str = ""
    jellyfin_api_key: str = ""
    jellyfin_username: str = ""
    jellyfin_password: str = ""
    playback_db: str = "/jellyfin-data/playback_reporting.db"
    jellyfin_db: str = "/jellyfin-data/jellyfin.db"
    cache_dir: str = "/cache"
    index_path: str = ""
    index_max_age_seconds: int = 3600
    index_limit_per_source: int = 5000
    index_history_days: int = 365
    default_algo: str = "blended"
    enable_llm_rerank: bool = False
    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.2:3b"
    taste_profile_path: str = "/cache/profiles/default.md"
    enable_profile_updates: bool = False
    profile_refresh_interval_seconds: int = 3600
    profile_chunk_events: int = 50
    profile_max_events_per_run: int = 1000
    profile_require_ollama: bool = False


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_settings() -> Settings:
    """Read settings from the current environment.

    Avoid resolving env vars at module import time so tests, CLI commands, and
    installer-generated configs can toggle optional features like LLM reranking
    without restarting the Python interpreter.
    """

    return Settings(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8787")),
        jellyfin_url=os.getenv("JELLYFIN_URL", ""),
        jellyfin_api_key=os.getenv("JELLYFIN_API_KEY", ""),
        jellyfin_username=os.getenv("JELLYFIN_USERNAME", ""),
        jellyfin_password=os.getenv("JELLYFIN_PASSWORD", ""),
        playback_db=os.getenv("PLAYBACK_DB", "/jellyfin-data/playback_reporting.db"),
        jellyfin_db=os.getenv("JELLYFIN_DB", "/jellyfin-data/jellyfin.db"),
        cache_dir=os.getenv("CACHE_DIR", "/cache"),
        index_path=os.getenv("INDEX_PATH", ""),
        index_max_age_seconds=int(os.getenv("INDEX_MAX_AGE_SECONDS", "3600")),
        index_limit_per_source=int(os.getenv("INDEX_LIMIT_PER_SOURCE", "5000")),
        index_history_days=int(os.getenv("INDEX_HISTORY_DAYS", "365")),
        default_algo=os.getenv("RECS_DEFAULT_ALGO", "blended"),
        enable_llm_rerank=env_bool("ENABLE_LLM_RERANK", False),
        ollama_url=os.getenv("OLLAMA_URL", "http://ollama:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
        taste_profile_path=os.getenv("TASTE_PROFILE_PATH", "/cache/profiles/default.md"),
        enable_profile_updates=env_bool("ENABLE_PROFILE_UPDATES", False),
        profile_refresh_interval_seconds=int(os.getenv("PROFILE_REFRESH_INTERVAL_SECONDS", "3600")),
        profile_chunk_events=int(os.getenv("PROFILE_CHUNK_EVENTS", "50")),
        profile_max_events_per_run=int(os.getenv("PROFILE_MAX_EVENTS_PER_RUN", "1000")),
        profile_require_ollama=env_bool("PROFILE_REQUIRE_OLLAMA", False),
    )
