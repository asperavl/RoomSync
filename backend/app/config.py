import os
import warnings
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/roomsync"
    SYNC_INTERVAL_SECONDS: int = 60
    MAX_SYNC_RETRIES: int = 3
    DEFAULT_MIN_NOTICE_MINUTES: int = 30
    DEFAULT_CANCELLATION_WINDOW_MINUTES: int = 15

    # Google OAuth 2.0 Settings
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/auth/google/callback"
    FRONTEND_URL: str = "http://localhost:5173"

    # JWT Authentication & Secret Keys
    JWT_SECRET_KEY: str = "roomsync-super-secure-jwt-key-2026-change-me"
    JWT_EXPIRATION_HOURS: int = 168  # 7 days

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

if settings.ENVIRONMENT == "production" and "change-me" in settings.JWT_SECRET_KEY:
    warnings.warn(
        "CRITICAL SECURITY WARNING: JWT_SECRET_KEY is using an insecure default value in production. "
        "Please set a cryptographically secure key in your environment.",
        RuntimeWarning,
        stacklevel=2,
    )
