import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

GARMIN_TOKENS_DIR = DATA_DIR / "garmin_tokens"
GARMIN_TOKENS_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "garmin_strava.db"


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

    # Garmin defaults (can be set via .env or Web UI)
    GARMIN_EMAIL: Optional[str] = None
    GARMIN_PASSWORD: Optional[str] = None

    # Strava API defaults (can be set via .env or Web UI)
    STRAVA_CLIENT_ID: Optional[str] = None
    STRAVA_CLIENT_SECRET: Optional[str] = None
    STRAVA_REDIRECT_URI: str = "http://localhost:8000/api/strava/callback"


settings = Settings()
