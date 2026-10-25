"""
Centralized application configuration.

All configuration is read from environment variables (see .env.example
at the repo root). Nothing here should be a hard-coded secret — Layer 1
security baseline (spec §53) requires secrets to come from the
environment, never from source.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Environment -------------------------------------------------
    ENVIRONMENT: str = "development"  # development | test | validation | production

    # --- Core services -------------------------------------------------
    DATABASE_URL: str = (
        "postgresql+psycopg2://raisa_synapse:devpassword_local_only"
        "@localhost:5432/raisa_synapse_dev"
    )
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Object storage (S3-compatible; MinIO for local dev) ----------
    OBJECT_STORAGE_ENDPOINT: str = "http://localhost:9000"
    OBJECT_STORAGE_BUCKET: str = "raisa-synapse-documents"
    OBJECT_STORAGE_ACCESS_KEY: str = "minioadmin"
    OBJECT_STORAGE_SECRET_KEY: str = "minioadmin"

    # --- Auth / security -------------------------------------------------
    AUTH_SECRET: str = "CHANGE_ME_DEV_ONLY_NOT_FOR_PRODUCTION"
    SESSION_SECRET: str = "CHANGE_ME_DEV_ONLY_NOT_FOR_PRODUCTION"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- URLs -------------------------------------------------
    APPLICATION_URL: str = "http://localhost:3000"
    API_URL: str = "http://localhost:8000"

    # --- CORS -------------------------------------------------
    CORS_ALLOW_ORIGINS: List[str] = ["http://localhost:3000"]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    """Settings are cached (a single instance per process) but this
    function stays easily overridable in tests via dependency
    overrides / monkeypatching lru_cache.
    """
    return Settings()
