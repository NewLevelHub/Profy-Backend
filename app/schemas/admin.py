import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.admin_result import AdminAnalysisResultResponse
from app.schemas.artifact import ArtifactItem
from app.schemas.profile import ProfileResponse
from app.schemas.roadmap import RoadmapResponse


class AdminUserListItem(BaseModel):
    id: uuid.UUID
    email: str
    is_verified: bool
    is_active: bool
    is_admin: bool
    created_at: datetime
    # Last seen, refreshed by any authenticated request (app/dependencies.py).
    # None means never seen since this started being recorded — for accounts
    # that predate it, the migration backfilled a floor from their newest
    # assessment or answer, so None there means no assessment either.
    last_active_at: datetime | None = None
    has_profile: bool
    profile_name: str | None = None
    age_group: str | None = None
    # A product for Kazakhstan makes "where do our users live" an obvious
    # question of any export, and neither field was reachable from this list.
    city: str | None = None
    grade: int | None = None
    assessments_count: int = 0
    latest_assessment_status: str | None = None
    latest_assessment_goal: str | None = None
    # From the profile's latest COMPLETED assessment's AnalysisResult, admin-
    # only raw percentages (TZ_Profi.md §18.3). `riasec` is None for junior
    # (whose instrument is MI, not RIASEC — deliberately not shown here) and
    # for users with no completed assessment yet. `big_five` is the raw
    # N/E/O/A/C dict (AnalysisResult.big_five), not the student-facing
    # flipped/relabeled `personality_profile` — admin sees true raw numbers,
    # same convention DiagnosticSummaryBlock already uses for RIASEC.
    riasec: dict[str, float] | None = None
    # Junior's interest instrument is MI, not RIASEC, so `riasec` is None for
    # every junior. Without this the export showed a completed junior
    # diagnostic as eleven empty score columns — indistinguishable from a
    # broken row rather than from a different instrument.
    mi: dict[str, float] | None = None
    big_five: dict[str, float] | None = None


class AdminUserListResponse(BaseModel):
    items: list[AdminUserListItem]
    total: int
    page: int
    limit: int


class AdminUserStatsResponse(BaseModel):
    """Counts that cannot be derived from a page of the users list, because
    each one is a question about the whole table — the reason the redesign
    had to drop a "BROUGHT ON DIAGNOSTICS: NO DATA" tile rather than fill it
    in on the client (docs/admin-backend-requests-pro-242.md §6).

    `completed_diagnostics` and `abandoned_diagnostics` count ASSESSMENTS,
    not users: one user can start several. `total` and `signups_last_7d`
    count users."""

    total: int
    signups_last_7d: int
    completed_diagnostics: int
    abandoned_diagnostics: int
    # Echoed back because it is a query parameter: "abandoned" is a judgement
    # about a threshold, not a fact, and the number on screen should say which
    # threshold produced it.
    inactive_days_threshold: int


class AdminAssessmentSummary(BaseModel):
    id: uuid.UUID
    goal: str
    status: str
    answered_count: int
    total_questions: int
    created_at: datetime
    completed_at: datetime | None = None
    has_result: bool = False
    has_roadmap: bool = False


class AdminUserDetailResponse(BaseModel):
    id: uuid.UUID
    email: str
    is_verified: bool
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_active_at: datetime | None = None
    profile: ProfileResponse | None = None
    artifacts: list[ArtifactItem] = []
    assessments: list[AdminAssessmentSummary] = []


class AdminResponseItem(BaseModel):
    question_id: uuid.UUID
    instrument: str
    category: str  # riasec_type letter or bigfive_domain letter, disambiguated by `instrument`
    question_text: str
    question_order: int
    answer_value: int
    selected_answer_text: str
    created_at: datetime


class AdminMotivationResponseItem(BaseModel):
    """One answered triplet: 3 statements were shown, the user picked one as
    MOST important and one as LEAST important — the third, untouched one is
    inferred (never stored as its own choice). All 3 text/category fields
    below are real answer data, not static triplet content — `picked_most_*`
    and `picked_least_*` are what the user actually clicked."""

    triplet_index: int
    picked_most_text: str
    picked_most_category: str
    picked_least_text: str
    picked_least_category: str
    not_picked_text: str
    not_picked_category: str
    created_at: datetime


class AdminAssessmentDetailResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    profile_name: str | None = None
    goal: str
    status: str
    answered_count: int
    total_questions: int
    created_at: datetime
    completed_at: datetime | None = None
    responses: list[AdminResponseItem] = []
    motivation_responses: list[AdminMotivationResponseItem] = []
    analysis_result: AdminAnalysisResultResponse | None = None
    roadmap: RoadmapResponse | None = None


class AdminListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)
    search: str | None = None


class AdminFeedbackListItem(BaseModel):
    """Feedback row alongside the submitting user's context — TZ_Profi.md
    §28.4. `assessment_id`/`age_group`/`scenario`/`top_direction_name` are
    all nullable: `assessment_id` is SET NULL if the assessment was deleted
    (feedback itself is never deleted with it), and the rest are only
    derivable when the assessment still exists and has a stored result."""

    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    profile_name: str | None = None
    assessment_id: uuid.UUID | None = None
    age_group: str | None = None
    scenario: str | None = None  # effective scenario A/B/C, see goal_overlay_service
    top_direction_name: str | None = None
    relevance_score: int
    helpful_sections: list[str]
    comment: str | None = None
    created_at: datetime


class AdminFeedbackListResponse(BaseModel):
    items: list[AdminFeedbackListItem]
    total: int
    page: int
    limit: int


class FeedbackBreakdownItem(BaseModel):
    key: str
    count: int
    avg_relevance_score: float


class AdminFeedbackStatsResponse(BaseModel):
    """TZ_Profi.md §28.4: "Результаты агрегируются в админке с разбивкой по
    возрасту, сценарию и топ-направлению." """

    total: int
    avg_relevance_score: float | None = None
    # Count per 1-5 score, keyed by the score as a string. The 1-5 histogram is
    # the main chart of the feedback screen, and an average alone cannot
    # reconstruct it — two very different distributions share a mean.
    score_counts: dict[str, int] = {}
    by_age_group: list[FeedbackBreakdownItem] = []
    by_scenario: list[FeedbackBreakdownItem] = []
    by_top_direction: list[FeedbackBreakdownItem] = []
    helpful_section_counts: dict[str, int] = {}
