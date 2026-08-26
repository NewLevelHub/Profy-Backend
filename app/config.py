from typing import Self
from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = ""
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    REDIS_URL: str
    SECRET_KEY: str
    LLM_API_KEY: str = ""
    # LLM (OpenAI) — off by default; roadmap falls back to templates when disabled.
    LLM_ENABLED: bool = False
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_TIMEOUT: float = 20.0
    LLM_MAX_TOKENS: int = 2000
    # The direction roadmap is a much larger generation (4 stages x 2 tracks x 3
    # tasks, each with a multi-sentence description) and does not fit the defaults
    # above. Under-sizing these truncates the JSON and the whole plan is discarded.
    # Both roadmap generators (goal + direction) use all three of these — they're
    # the densest, highest-value generations in the app, worth a stronger/pricier
    # model than the default used for lighter calls (inquiry questions, verdicts,
    # report summary).
    LLM_ROADMAP_TIMEOUT: float = 150.0
    LLM_ROADMAP_MAX_TOKENS: int = 8000
    LLM_ROADMAP_MODEL: str = "gpt-4.1"
    LLM_TEMPERATURE: float = 0.3
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = ""

    # Object storage (S3-compatible — MinIO locally, any real S3/R2/Spaces in
    # prod; same code path, only these values differ per environment).
    STORAGE_ENDPOINT_URL: str | None = None
    STORAGE_REGION: str = "us-east-1"
    STORAGE_ACCESS_KEY: str = ""
    STORAGE_SECRET_KEY: str = ""
    STORAGE_BUCKET: str = "profi-media"
    STORAGE_USE_PATH_STYLE: bool = True
    # The read-path base the browser actually hits (nginx locally, a
    # CDN/bucket-website domain in prod) — distinct from STORAGE_ENDPOINT_URL
    # above, which is the write-path boto3 talks to and is often internal.
    STORAGE_PUBLIC_BASE_URL: str = "http://localhost/media"

    # University photo import (scripts/import_jinaq_university_photos.py).
    SCRAPER_USER_AGENT: str = "ProfyUniversityPhotoBot/1.0"
    SCRAPER_REQUEST_DELAY_SECONDS: float = 1.0
    SCRAPER_REQUEST_TIMEOUT_SECONDS: float = 20.0
    # Real domain of the jinaq source site — imageUrl in universities.json is
    # a relative path (e.g. "/cdn/jinaq-media/institutions/3109/image.webp");
    # this is prepended to build the absolute download URL. Fill in before
    # running scripts/import_jinaq_university_photos.py for real.
    JINAQ_MEDIA_BASE_URL: str = "https://TODO-set-real-jinaq-domain"

    @model_validator(mode="after")
    def build_database_url(self) -> Self:
        if self.DATABASE_URL:
            return self
        if not self.POSTGRES_USER or not self.POSTGRES_DB:
            raise ValueError("Set DATABASE_URL or POSTGRES_USER/POSTGRES_DB")
        user = quote_plus(self.POSTGRES_USER)
        password = quote_plus(self.POSTGRES_PASSWORD)
        self.DATABASE_URL = (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
        return self


settings = Settings()
