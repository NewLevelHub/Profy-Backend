import json
from pathlib import Path
from typing import Self
from urllib.parse import quote_plus

from pydantic import BaseModel, ConfigDict, model_validator
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
    # Public SPA origin for deep links in transactional emails (no trailing slash).
    FRONTEND_URL: str = "http://localhost:5173"
    GOOGLE_CLIENT_ID: str = ""

    # Which backend build_storage_backend() returns:
    #   "fs"  — write photos to STORAGE_FS_ROOT on disk; nginx serves them
    #           directly (default; no object-storage service to run).
    #   "s3"  — talk to the S3-compatible endpoint below (MinIO / real
    #           S3 / R2 / Spaces).
    STORAGE_BACKEND: str = "fs"
    # "fs" backend: directory the photos are written to. MUST be the same
    # directory nginx serves at STORAGE_PUBLIC_BASE_URL — in Docker the one
    # host folder is bind-mounted into api (read-write) and nginx
    # (read-only); see docker-compose.yml. This is the in-container path.
    STORAGE_FS_ROOT: str = "/srv/media"

    # "s3" backend (unused while STORAGE_BACKEND=fs). STORAGE_ENDPOINT_URL is
    # the write-path boto3 talks to and is often internal.
    STORAGE_ENDPOINT_URL: str | None = None
    STORAGE_REGION: str = "us-east-1"
    STORAGE_ACCESS_KEY: str = ""
    STORAGE_SECRET_KEY: str = ""
    STORAGE_BUCKET: str = "profi-media"
    STORAGE_USE_PATH_STYLE: bool = True
    # The read-path base the browser actually hits: nginx's /media/ locally,
    # a CDN / bucket-website domain in prod. Independent of the backend —
    # build_public_url() just prepends it to the stored storage_key.
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





# --- Psychoemotional (МЦВ Собчик) thresholds (epic PRO-282, phase 2; PRO-305)
# Same contract as validity_thresholds: soft-level cut-offs + run-validity
# signal limits in a versioned JSON, edited without code changes
# (psych-block-spec.md §B6/§B7). The engine (PRO-309) writes the applied
# `version` onto psychoemotional_runs.thresholds_version.
_PSYCHOEMOTIONAL_THRESHOLDS_PATH = (
    Path(__file__).parent / "data" / "psychoemotional_thresholds.json"
)


class PsychoEmotionalThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    version: int
    so: dict[str, int]  # {norm_max, elevated_max} — СО 0–32
    anxiety: dict[str, int]  # {low_max, moderate_max} — индекс тревоги 0–12
    compensation: dict[str, int]  # {norm_max, moderate_max} — индекс компенсации 0–9
    vk: dict[str, float]  # {exhaustion_max, norm_max} — ВК 0.2–5.0
    validity: dict[str, float]  # §B7 / PRO-308: median_dt_ms_mechanical / total_fast_sec / split_pairs_unstable / d_unstable / pause_min_sec


def load_psychoemotional_thresholds(
    path: Path = _PSYCHOEMOTIONAL_THRESHOLDS_PATH,
) -> PsychoEmotionalThresholds:
    return PsychoEmotionalThresholds.model_validate(
        json.loads(path.read_text(encoding="utf-8"))
    )


psychoemotional_thresholds: PsychoEmotionalThresholds = load_psychoemotional_thresholds()


# --- Eysenck EPI thresholds (epic PRO-338, phase 1; Ф1.5) -------------------
# Same contract as validity_thresholds/psychoemotional_thresholds: cut-offs
# in a versioned JSON, edited without code changes
# (02-Фаза1-Лёгкие-тесты.md §1.Б). eysenck_service.py stores the applied
# `version` alongside the computed scores.
_EYSENCK_THRESHOLDS_PATH = Path(__file__).parent / "data" / "eysenck_thresholds.json"


class EysenckThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    version: int
    lie_scale_max_ok: int  # lie_raw > this -> protocol flagged ("traffic light")
    # Ascending inclusive upper bounds for every band except the last one
    # (which is "greater than the last bound"):
    #   extraversion_bounds [4, 8, 14, 19] -> <=4 deep_introvert, 5-8
    #   introvert, 9-14 ambivert, 15-19 extravert, >19 bright_extravert.
    extraversion_bounds: tuple[int, int, int, int]
    #   neuroticism_bounds [8, 13, 19] -> <=8 low, 9-13 medium, 14-19 high,
    #   >19 very_high.
    neuroticism_bounds: tuple[int, int, int]

    def lie_scale_flagged(self, lie_raw: int) -> bool:
        return lie_raw > self.lie_scale_max_ok

    def extraversion_level(self, raw: int) -> str:
        labels = ["deep_introvert", "introvert", "ambivert", "extravert"]
        for bound, label in zip(self.extraversion_bounds, labels):
            if raw <= bound:
                return label
        return "bright_extravert"

    def neuroticism_level(self, raw: int) -> str:
        labels = ["low", "medium", "high"]
        for bound, label in zip(self.neuroticism_bounds, labels):
            if raw <= bound:
                return label
        return "very_high"


def load_eysenck_thresholds(
    path: Path = _EYSENCK_THRESHOLDS_PATH,
) -> EysenckThresholds:
    return EysenckThresholds.model_validate(json.loads(path.read_text(encoding="utf-8")))


eysenck_thresholds: EysenckThresholds = load_eysenck_thresholds()


# --- Elers achievement-motivation thresholds (epic PRO-338, phase 1; Ф1.8) --
# Same contract as eysenck_thresholds/validity_thresholds: cut-offs in a
# versioned JSON, edited without code changes (02-Фаза1-Лёгкие-тесты.md §1.В).
_ELERS_THRESHOLDS_PATH = Path(__file__).parent / "data" / "elers_thresholds.json"


class ElersThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    version: int
    # Ascending inclusive upper bounds for every band except the last one
    # (which is "greater than the last bound"):
    #   bounds [10, 16, 20] -> 1-10 low, 11-16 medium, 17-20 moderately_high
    #   (positive prognostic marker), >20 too_high (burnout risk).
    bounds: tuple[int, int, int]

    def level(self, raw: int) -> str:
        labels = ["low", "medium", "moderately_high"]
        for bound, label in zip(self.bounds, labels):
            if raw <= bound:
                return label
        return "too_high"


def load_elers_thresholds(
    path: Path = _ELERS_THRESHOLDS_PATH,
) -> ElersThresholds:
    return ElersThresholds.model_validate(json.loads(path.read_text(encoding="utf-8")))


elers_thresholds: ElersThresholds = load_elers_thresholds()


# --- Boyko empathy thresholds (epic PRO-338, phase 1; Ф1.11) ----------------
# Same contract as elers_thresholds/eysenck_thresholds: cut-offs in a
# versioned JSON, edited without code changes (02-Фаза1-Лёгкие-тесты.md §1.Г).
_BOYKO_EMPATHY_THRESHOLDS_PATH = Path(__file__).parent / "data" / "boyko_empathy_thresholds.json"


class BoykoEmpathyThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    version: int
    # Ascending inclusive upper bounds for every band except the last one
    # (which is "greater than the last bound"):
    #   bounds [14, 21, 29] -> <=14 very_low, 15-21 underestimated,
    #   22-29 average, >29 (30-36) very_high. See the JSON file's own
    #   comment for how the ambiguous boundary score 14 was resolved.
    bounds: tuple[int, int, int]

    def level(self, raw: int) -> str:
        labels = ["very_low", "underestimated", "average"]
        for bound, label in zip(self.bounds, labels):
            if raw <= bound:
                return label
        return "very_high"


def load_boyko_empathy_thresholds(
    path: Path = _BOYKO_EMPATHY_THRESHOLDS_PATH,
) -> BoykoEmpathyThresholds:
    return BoykoEmpathyThresholds.model_validate(json.loads(path.read_text(encoding="utf-8")))


boyko_empathy_thresholds: BoykoEmpathyThresholds = load_boyko_empathy_thresholds()


# --- Kondash/Prikhozhan anxiety -> confidence thresholds (epic PRO-338,
# phase 1; Ф1.11) --------------------------------------------------------
# Same contract as the thresholds above: cut-offs in a versioned JSON, edited
# without code changes. See the JSON file's own comment for the age-bracket
# and inversion-semantics decisions.
_KONDASH_ANXIETY_THRESHOLDS_PATH = Path(__file__).parent / "data" / "kondash_anxiety_thresholds.json"


class KondashAgeBracket(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_age: int
    sten10: int


class KondashAnxietyThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    version: int
    interpersonal_sten10_by_age: tuple[KondashAgeBracket, ...]
    # Ascending inclusive upper bounds: sten<=bounds[0] "high" confidence,
    # sten<=bounds[1] "normative", above that "low".
    confidence_sten_bounds: tuple[int, int]

    def interpersonal_sten10(self, age: int) -> int:
        """Sten-10 raw-score threshold for the межличностная subscale at
        this age — the last bracket also serves as the fallback for any age
        past its `max_age` (see the JSON file's own comment)."""
        for bracket in self.interpersonal_sten10_by_age:
            if age <= bracket.max_age:
                return bracket.sten10
        return self.interpersonal_sten10_by_age[-1].sten10

    def confidence_level(self, sten: int) -> str:
        labels = ["high", "normative"]
        for bound, label in zip(self.confidence_sten_bounds, labels):
            if sten <= bound:
                return label
        return "low"


def load_kondash_anxiety_thresholds(
    path: Path = _KONDASH_ANXIETY_THRESHOLDS_PATH,
) -> KondashAnxietyThresholds:
    return KondashAnxietyThresholds.model_validate(json.loads(path.read_text(encoding="utf-8")))


kondash_anxiety_thresholds: KondashAnxietyThresholds = load_kondash_anxiety_thresholds()


# --- Belbin BTRSPI role-interpretation threshold (epic PRO-338, phase 2; Ф2.5) --
# Same contract as eysenck_thresholds/elers_thresholds: cut-off in a
# versioned JSON, edited without code changes
# (03-Фаза2-Белбин.md Ф2.5).
_BELBIN_THRESHOLDS_PATH = Path(__file__).parent / "data" / "belbin_thresholds.json"


class BelbinThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    version: int
    # role_totals[role] <= this -> "avoidance zone" (delegate to others).
    avoidance_max_score: int

    def is_avoidance_zone(self, role_score: int) -> bool:
        return role_score <= self.avoidance_max_score


def load_belbin_thresholds(
    path: Path = _BELBIN_THRESHOLDS_PATH,
) -> BelbinThresholds:
    return BelbinThresholds.model_validate(json.loads(path.read_text(encoding="utf-8")))


belbin_thresholds: BelbinThresholds = load_belbin_thresholds()


# --- АСТУР timer engine config (epic PRO-338, phase 3; Ф3.4) ---------------
# Same contract as belbin_thresholds/eysenck_thresholds: a number in a
# versioned JSON, edited without code changes (04-Фаза3-АСТУР.md Ф3.4).
_ASTUR_TIMER_CONFIG_PATH = Path(__file__).parent / "data" / "astur_timer_config.json"


class AsturTimerConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    version: int
    # elapsed_ms > this on one lability command -> item_over_limit() True.
    lability_item_limit_ms: int
    # Per-subtest soft budget in seconds (Ф3.6's frontend countdown) — every
    # `SUBTESTS` key except "lability" (which uses lability_item_limit_ms
    # per command instead of a whole-subtest budget). A UI nudge only, not
    # a server-enforced cutoff — see the JSON file's own comment.
    subtest_time_limit_sec: dict[str, int] = {}


def load_astur_timer_config(
    path: Path = _ASTUR_TIMER_CONFIG_PATH,
) -> AsturTimerConfig:
    return AsturTimerConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))


astur_timer_config: AsturTimerConfig = load_astur_timer_config()


# --- АСТУР СПН-group thresholds (epic PRO-338, phase 3; Ф3.5) --------------
# Same contract as belbin_thresholds/eysenck_thresholds: cut-offs in a
# versioned JSON, edited without code changes (04-Фаза3-АСТУР.md Ф3.5).
_ASTUR_THRESHOLDS_PATH = Path(__file__).parent / "data" / "astur_thresholds.json"


class AsturThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    version: int
    # Ascending inclusive upper bounds for groups 5,4,3,2 (in that order —
    # СПН group numbering is BEST=1/WORST=5, the opposite direction from
    # raw_score): raw<=bounds[0] -> group 5 (worst), raw<=bounds[1] -> 4,
    # raw<=bounds[2] -> 3, raw<=bounds[3] -> 2, raw>bounds[3] -> group 1 (best).
    spn_bounds: tuple[int, int, int, int]

    def spn_group(self, raw_score: int) -> int:
        labels = [5, 4, 3, 2]
        for bound, label in zip(self.spn_bounds, labels):
            if raw_score <= bound:
                return label
        return 1


def load_astur_thresholds(
    path: Path = _ASTUR_THRESHOLDS_PATH,
) -> AsturThresholds:
    return AsturThresholds.model_validate(json.loads(path.read_text(encoding="utf-8")))


astur_thresholds: AsturThresholds = load_astur_thresholds()
