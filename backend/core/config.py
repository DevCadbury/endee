# =============================================================================
# core/config.py — Application Configuration (Pydantic BaseSettings)
# =============================================================================
# Loads all environment variables from .env file with type validation.
# Single source of truth for all configurable parameters.
# =============================================================================

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    All values can be overridden via .env file or system env vars.
    """

    # --- Google Gemini LLM Configuration ---
    GEMINI_API_KEY: str = ""
    LLM_MODEL: str = "gemini-2.0-flash"

    # --- Endee Vector Database ---
    ENDEE_URL: str = "http://localhost:8080"
    ENDEE_INDEX_NAME: str = "support_kb"

    # --- MongoDB ---
    MONGODB_URL: str = "mongodb://localhost:27017/support_ai"

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379"

    # --- Embedding Model ---
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"

    # --- Decision Thresholds ---
    # Scores above this → auto-resolve with RAG answer
    AUTO_RESOLVE_THRESHOLD: float = 0.82
    # Scores between CLARIFY and AUTO_RESOLVE → ask clarifying question
    CLARIFY_THRESHOLD: float = 0.60

    # --- JWT Auth ---
    JWT_SECRET: str = "change-this-to-a-strong-random-string-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24 hours

    # --- Rate Limiting ---
    RATE_LIMIT_REQUESTS: int = 20
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Cached settings loader. Returns the same Settings instance
    across all calls to avoid re-reading .env on every request.
    """
    return Settings()
