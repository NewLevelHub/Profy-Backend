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
    # LLM (OpenAI) — off by default when unset; there is no template fallback
    # (see roadmap_builder.generate_direction_roadmap) — disabled/failed
    # generation surfaces as a 503 the frontend already renders as a friendly
    # "ИИ временно недоступен" retry screen (DirectionRoadmapPage.tsx).
    LLM_ENABLED: bool = False
    # gpt-4o-mini was too weak to reliably follow this prompt's structural
    # rules (exactly 4 stages, per-stage track coverage) and evidence-grounding
    # rules for growth_focus — gpt-4.1 follows long, rule-heavy instructions
    # more consistently. Both support OpenAI Structured Outputs (strict JSON
    # schema); swap freely via env, no code change needed.
    LLM_MODEL: str = "gpt-4.1"
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_TIMEOUT: float = 20.0
    LLM_MAX_TOKENS: int = 2000
    # The direction roadmap is a much larger generation (4 stages x 3-5 steps,
    # each with a multi-sentence description) and does not fit the defaults
    # above. Under-sizing these truncates the JSON and the whole plan is
    # discarded. Bumped alongside the model change: a stronger model tends to
    # be more verbose, and Russian text tokenizes heavier than English.
    LLM_ROADMAP_TIMEOUT: float = 180.0
    LLM_ROADMAP_MAX_TOKENS: int = 10000
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
    # Retuned again (calibration pass 3, 2026-07): match_score is now
    # normalized by the leaf's profile norm (see akinator_engine.match_score
    # docstring — fixes "loud profile always wins" regardless of fit), which
    # shrank typical per-answer scores roughly 5-8x (old raw dot products
    # ranged ~0-12, normalized scores range ~-2 to +3).
    #
    # 2.0 (restoring the old ~8-question average) was tried first, but a
    # "textbook persona per real profession" census (scripts/calibration_simulate.py
    # --census) showed it made *targeting accuracy* worse, not better: 55%
    # of professions failed to land in the top-3 by final belief, vs 31% at
    # the old (too-slow) beta=0.3. Reason: converging fast leaves no time for
    # a profession's real signal to outweigh incidental overlap with
    # unrelated leaves on shared axes. 1.2 is the middle point chosen instead
    # — slower (~15-16 questions for senior) but 43% census failure, a real
    # improvement traded for a longer test. Product decision, not a pure
    # technical one: short test vs. better-matched results.
    AKINATOR_BETA: float = 1.2
    # Stopping criterion (see akinatorLogic/profi_axes_phase1.md "Критерий
    # остановки"): single leaf if top1 > T and top1 >= M * top2; otherwise a
    # cluster of up to K leaves once their cumulative belief reaches the
    # threshold. Retuned alongside AKINATOR_BETA (see note above) — old
    # T=0.45/M=1.5/threshold=0.70 were crossed within 2-3 answers. T/M/
    # threshold themselves didn't need to change again in pass 3 (only beta
    # did) — they compare belief *proportions*, which the score normalization
    # doesn't change the scale of, only how fast beliefs move per answer.
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
    # ceiling. Bumped again in calibration pass 3 (10/14/18 -> 18/20/22):
    # beta dropped to 1.2 (see AKINATOR_BETA) to trade test length for
    # accuracy, so every age needs more runway to reach the same confidence
    # bar. Junior still lands on "cluster via ceiling" more often than not
    # even at 18 (~64% of the time) — it only draws from the ~31
    # age_variant="both" questions, the smaller/blunter half of the bank; a
    # gentler, less-decisive outcome for younger ages, not a bug, but still
    # worth a junior/middle-specific disambiguator-question follow-up if that
    # ratio needs to improve.
    AKINATOR_CEILING_JUNIOR: int = 18
    AKINATOR_CEILING_MIDDLE: int = 20
    AKINATOR_CEILING_SENIOR: int = 22
    # Question-selection temperature (calibration pass 2, 2026-07): past
    # WIDE_START_STEPS, the engine used to always pick the single question
    # with strictly minimum expected posterior entropy — real session logs
    # showed this made a handful of sharply-worded resolves_pair questions
    # "the best" for nearly every session regardless of the user's own
    # answers (out of 45 questions, ~10 got picked 700-1700+ times across
    # ~3000 sessions while others got picked under 15 times). Now a weighted
    # random pick favoring low entropy, not a strict argmin — low value ~=
    # near-deterministic (old behavior), high value ~= uniform random. 0.2
    # picked by sweeping 0.1-0.5 against simulated sessions: every question
    # in the bank gets used, and average length stays ~9-10 questions
    # (vs. 12+ at higher temperatures, where too much randomness hurts
    # information efficiency and pushes sessions toward their age ceiling).
    AKINATOR_QUESTION_TEMPERATURE: float = 0.2

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
