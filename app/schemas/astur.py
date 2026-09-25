"""АСТУР contracts: attempt lifecycle API (PRO-338 Ф3.4 → PRO-427) and the
result snapshot frozen once when an attempt is finalized."""
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RunStatus = Literal["in_progress", "completed", "invalidated"]
# Per-item outcome kept in the snapshot: `unanswered` = no explicit answer
# or skip was recorded (legacy protocols, blank values), `skipped` = the
# respondent explicitly skipped the item.
ItemStatus = Literal["correct", "partial", "wrong", "skipped", "unanswered"]


# ── Result snapshot ─────────────────────────────────────────────────────────


class SubtestResult(BaseModel):
    key: str
    score: float
    max_score: int
    percent: float
    item_count: int
    answered: int
    skipped: int = 0
    unanswered: int = 0
    # Counted in `overall_percent` under this snapshot's scoring version.
    in_overall: bool


class SubjectAreaResult(BaseModel):
    key: str
    earned: float
    item_count: int
    answered: int
    percent: float


class SubjectProfileResult(BaseModel):
    """Knowledge of subject-area terms (Осведомлённость + Обобщение), not
    ability — see `MathReasoningResult` for number problems."""

    status: Literal["leading", "mixed", "insufficient_data"]
    leading: str | None = None
    runner_up: str | None = None
    gap_pp: float | None = None
    threshold_pp: float | None = None
    areas: list[SubjectAreaResult]


class MathReasoningResult(BaseModel):
    """Number-series pattern recognition next to physics/math knowledge."""

    numeric_series_percent: float
    physics_math_knowledge_percent: float | None = None
    # knowledge − pattern recognition, in percentage points.
    gap_pp: float | None = None
    divergence: Literal["none", "knowledge_higher", "reasoning_higher"] | None = None
    threshold_pp: float


class QuickInstructionsResult(BaseModel):
    """Observed accuracy on the timed commands. A command counts as correct
    only when it is both right and answered within its time limit."""

    status: Literal["ok", "insufficient_on_time"]
    total: int
    on_time: int
    skipped: int = 0
    first_half_correct: int
    first_half_total: int
    second_half_correct: int
    second_half_total: int
    first_half_percent: float | None = None
    second_half_percent: float | None = None
    accuracy_change_pp: float | None = None
    mean_ms: int | None = None
    median_ms: int | None = None
    # Server-observed duration of the whole block vs the sum of the
    # client-reported per-command times (client timing is an observation,
    # not a protected measurement).
    server_block_ms: int | None = None
    client_total_ms: int | None = None


class ProtocolFlag(BaseModel):
    code: str
    subtest: str | None = None
    count: int | None = None


class ProtocolQuality(BaseModel):
    ok: bool
    flags: list[ProtocolFlag] = Field(default_factory=list)


class AttemptHistory(BaseModel):
    """Where this attempt sits among the respondent's АСТУР attempts. A
    repeat exposure to the same form means a changed score may come from
    familiarity with the items, not from a changed skill."""

    attempt_number: int = 1
    repeat_exposure: bool = False
    days_since_previous: int | None = None


class AsturResultSnapshot(BaseModel):
    scoring_version: str
    bank_version: int
    legacy: bool = False
    completed_at: datetime
    age_at_completion: int | None = None
    grade_at_completion: int | None = None
    history: AttemptHistory = Field(default_factory=AttemptHistory)
    subtests: list[SubtestResult]
    overall_percent: float | None
    subject_profile: SubjectProfileResult
    math_reasoning: MathReasoningResult | None = None
    quick_instructions: QuickInstructionsResult | None = None
    protocol_quality: ProtocolQuality
    # item_id -> earned points / outcome; feed per-item analytics, never the report.
    item_scores: dict[str, float] = Field(default_factory=dict)
    item_status: dict[str, ItemStatus] = Field(default_factory=dict)


# ── Attempt lifecycle API ───────────────────────────────────────────────────


class AsturRunSummary(BaseModel):
    run_id: uuid.UUID
    status: RunStatus
    bank_version: int
    # Language the attempt's content and keys are pinned to.
    locale: str
    created_at: datetime
    completed_at: datetime | None = None
    submitted_subtests: list[str]
    # First server start for every currently unfinished subtest. The client
    # resumes its countdown from this anchor after a reload.
    subtest_started_at: dict[str, str]


class AsturStateResponse(BaseModel):
    """What the test-taker's UI needs to pick a screen: `not_started` (no
    attempt ever), `in_progress` (an attempt is open — resume it), or
    `completed` (a finished attempt exists and none is open)."""

    status: Literal["not_started", "in_progress", "completed"]
    active_run: AsturRunSummary | None = None
    latest_completed_run: AsturRunSummary | None = None


class OpenAsturAttemptRequest(BaseModel):
    # True = explicit «Пройти заново» after a completed attempt. Without it,
    # a completed attempt is never silently followed by a new one.
    retake: bool = False

    model_config = {"extra": "forbid"}


class AsturContentSubtest(BaseModel):
    """One subtest's renderable content. Item shape varies by `key`; never
    carries an answer key or a reviewer field."""

    number: int
    key: str
    name: str
    instruction: str
    item_count: int
    time_limit_sec: int | None
    items: list[dict[str, Any]]


class AsturContentResponse(BaseModel):
    run_id: uuid.UUID
    bank_version: int
    locale: str
    subtests: list[AsturContentSubtest]
    lability_item_limit_ms: int


class AsturAttemptResponse(BaseModel):
    """The open attempt and its content — returned together so the items
    shown are always the ones of the attempt's own bank version and locale."""

    run: AsturRunSummary
    content: AsturContentResponse


class StartAsturSubtestRequest(BaseModel):
    run_id: uuid.UUID

    model_config = {"extra": "forbid"}


class StartAsturSubtestResponse(BaseModel):
    run_id: uuid.UUID
    subtest: str
    started_at: str  # ISO 8601, server clock — the timer engine's anchor


class AsturItemAnswer(BaseModel):
    """One item's outcome: an explicit answer or an explicit skip. A blank
    value is never an answer — skipping is its own, visible choice."""

    status: Literal["answered", "skipped"]
    value: Any = None

    model_config = {"extra": "forbid"}


class SubmitAsturSubtestRequest(BaseModel):
    # The attempt the respondent is actually answering — a submit meant for
    # another (stale or finished) attempt is rejected, never re-targeted.
    run_id: uuid.UUID
    # 1-based item position (as string) -> answer or skip.
    answers: dict[str, AsturItemAnswer]
    # Quick instructions only: client-measured time per command (ms).
    elapsed_ms: dict[str, int] | None = None
    # Quick instructions only: the respondent's IANA timezone, so a
    # day-of-week command is checked against their local calendar day.
    client_timezone: str | None = Field(default=None, max_length=64)

    model_config = {"extra": "forbid"}


class SubmitAsturSubtestResponse(BaseModel):
    run_id: uuid.UUID
    subtest: str
    # None if .../start was never called for this subtest.
    actual_ms: int | None
    over_limit_items: list[str] = Field(default_factory=list)
    # True when the attempt is completed (this submit, or an identical
    # earlier one, froze the result).
    run_completed: bool = False
