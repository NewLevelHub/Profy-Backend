from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine.url import URL


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
    # Retuned (calibration pass 1, 2026-07): 0.7 made belief swing so hard per
    # answer that sessions reveal_single'd after 2-3 questions on average
    # (log-domain updates over 82 leaves starting at 1/82 amplify fast through
    # softmax). 0.3 was picked by simulating ~150 randomized-answer sessions
    # and sweeping beta/T/M/cluster_threshold until the average settled
    # around 7-8 questions with a healthy single/cluster mix.
    AKINATOR_BETA: float = 0.3
    # Stopping criterion (see akinatorLogic/profi_axes_phase1.md "Критерий
    # остановки"): single leaf if top1 > T and top1 >= M * top2; otherwise a
    # cluster of up to K leaves once their cumulative belief reaches the
    # threshold. Retuned alongside AKINATOR_BETA (see note above) — old
    # T=0.45/M=1.5/threshold=0.70 were crossed within 2-3 answers.
    AKINATOR_STOP_T: float = 0.58
    AKINATOR_STOP_M: float = 2.0
    AKINATOR_STOP_CLUSTER_K: int = 3
    AKINATOR_STOP_CLUSTER_THRESHOLD: float = 0.78
    # Age-based question ceilings (safety net) — junior gets a softer "направление"
    # sooner, senior can go deeper before we force a cluster reveal. Bumped
    # junior/middle up from 8/12: check_stop now requires every axis family to
    # be touched at least once before a confidence-based reveal is even
    # possible (calibration pass 1), and junior/middle only draw from the ~29
    # age_variant="both" questions (senior-only ones are the sharpest
    # disambiguators) — 8/12 left almost no room for confidence to build
    # after covering all 5 families, so those ages always bottomed out at the
    # ceiling. 10/14 leaves more runway; they may still often land on
    # "cluster via ceiling" rather than a single confident pick given the
    # smaller question pool — a gentler outcome for younger ages, not a bug,
    # but the lack of junior/middle-specific disambiguator questions is worth
    # a content follow-up.
    AKINATOR_CEILING_JUNIOR: int = 10
    AKINATOR_CEILING_MIDDLE: int = 14
    AKINATOR_CEILING_SENIOR: int = 18

    @model_validator(mode="after")
    def build_database_url(self) -> Self:
        if self.DATABASE_URL:
            return self
        if not self.POSTGRES_USER or not self.POSTGRES_DB:
            raise ValueError("Set DATABASE_URL or POSTGRES_USER/POSTGRES_DB")
        # URL.create encodes special chars in password (@, !, etc.) correctly —
        # raw f-strings break asyncpg auth when password contains '@'.
        self.DATABASE_URL = URL.create(
            drivername="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        ).render_as_string(hide_password=False)
        return self


settings = Settings()
