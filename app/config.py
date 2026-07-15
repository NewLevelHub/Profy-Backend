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
    LLM_ROADMAP_TIMEOUT: float = 150.0
    LLM_ROADMAP_MAX_TOKENS: int = 8000
    LLM_TEMPERATURE: float = 0.3
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = ""
    # Belief update step size (see akinatorLogic/profi_axes_phase1.md "Формула
    # апдейта"): log belief(L) += AKINATOR_BETA * match(A, L). Start ≈0.7, tune by log.
    AKINATOR_BETA: float = 0.7
    # Stopping criterion (see akinatorLogic/profi_axes_phase1.md "Критерий
    # остановки"): single leaf if top1 > T and top1 >= M * top2; otherwise a
    # cluster of up to K leaves once their cumulative belief reaches the
    # threshold. All starting values, calibrate by log like AKINATOR_BETA.
    AKINATOR_STOP_T: float = 0.45
    AKINATOR_STOP_M: float = 1.5
    AKINATOR_STOP_CLUSTER_K: int = 3
    AKINATOR_STOP_CLUSTER_THRESHOLD: float = 0.70
    # Age-based question ceilings (safety net) — junior gets a softer "направление"
    # sooner, senior can go deeper before we force a cluster reveal. Placeholder
    # starting points, no calibration data yet.
    AKINATOR_CEILING_JUNIOR: int = 8
    AKINATOR_CEILING_MIDDLE: int = 12
    AKINATOR_CEILING_SENIOR: int = 18

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
