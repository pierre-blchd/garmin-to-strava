import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Garmin session tokens are still stored on local disk per-user (not DB-backed)
GARMIN_TOKENS_DIR = DATA_DIR / "garmin_tokens"
GARMIN_TOKENS_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Web server
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    SECRET_KEY: str = "default-garmin-to-strava-secret-key-12345"
    COOKIE_SECURE: bool = False  # Set to True if behind HTTPS proxy in production

    # Database (PostgreSQL)
    # Full DSN takes precedence; falls back to the discrete PG* fields if unset.
    DATABASE_URL: Optional[str] = None
    PGHOST: str = "localhost"
    PGPORT: int = 5432
    PGDATABASE: str = "garmin_strava"
    PGUSER: str = "garmin_strava_app"
    PGPASSWORD: str = ""
    DB_POOL_MIN_CONN: int = 1
    DB_POOL_MAX_CONN: int = 10

    # Garmin defaults (can be set via .env or Web UI)
    GARMIN_EMAIL: Optional[str] = None
    GARMIN_PASSWORD: Optional[str] = None

    # Comma-separated garminconnect login strategies to skip (speeds up login by
    # avoiding strategies that are systematically rate-limited/blocked for your IP
    # before falling through to a working one). Valid names: mobile+cffi,
    # mobile+requests, widget+cffi, portal+cffi, portal+requests.
    # Empty string disables skipping (tries every strategy, slowest but most robust).
    GARMIN_SKIP_LOGIN_STRATEGIES: str = "mobile+cffi,mobile+requests"

    # Strava API defaults (can be set via .env or Web UI)
    STRAVA_CLIENT_ID: Optional[str] = None
    STRAVA_CLIENT_SECRET: Optional[str] = None
    STRAVA_REDIRECT_URI: str = "http://localhost:8000/api/strava/callback"

    @property
    def database_dsn(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql://{self.PGUSER}:{self.PGPASSWORD}"
            f"@{self.PGHOST}:{self.PGPORT}/{self.PGDATABASE}"
        )


settings = Settings()
