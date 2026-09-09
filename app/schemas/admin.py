import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.user import UserRole
from app.schemas.admin_result import AdminAnalysisResultResponse
from app.schemas.artifact import ArtifactItem
from app.schemas.auth import NormalizedEmail, _validate_password_complexity
from app.schemas.profile import ProfileResponse
from app.schemas.roadmap import RoadmapResponse


class AdminUserListItem(BaseModel):
    id: uuid.UUID
    email: str
    is_verified: bool
    is_active: bool
    role: UserRole
    is_admin: bool
    created_at: datetime
    has_profile: bool
    profile_name: str | None = None
    age_group: str | None = None
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
    big_five: dict[str, float] | None = None


class AdminUserListResponse(BaseModel):
    items: list[AdminUserListItem]
    total: int
    page: int
    limit: int


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
    role: UserRole
    is_admin: bool
    created_at: datetime
    profile: ProfileResponse | None = None
    artifacts: list[ArtifactItem] = []
    assessments: list[AdminAssessmentSummary] = []


class AdminUserCreate(BaseModel):
    """Admin-only provisioning of admin/psychologist accounts — self-registration
    (POST /auth/register) remains the only path that creates a `student`."""

    email: NormalizedEmail
    password: str = Field(min_length=8)
    role: UserRole
    is_verified: bool = True

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _validate_password_complexity(v)

    @field_validator("role")
    @classmethod
    def role_not_student(cls, v: UserRole) -> UserRole:
        if v == UserRole.student:
            raise ValueError("Use /auth/register to create student accounts")
        return v


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
    by_age_group: list[FeedbackBreakdownItem] = []
    by_scenario: list[FeedbackBreakdownItem] = []
    by_top_direction: list[FeedbackBreakdownItem] = []
    helpful_section_counts: dict[str, int] = {}


class PsychologistAssignmentCreate(BaseModel):
    """Admin-only link between a psychologist and a student (PRO-326).

    Role validation happens in the service layer on create — not here and
    not as a DB constraint (see PsychologistStudentAssignment).
    """

    psychologist_id: uuid.UUID
    student_id: uuid.UUID


class PsychologistAssignmentItem(BaseModel):
    id: uuid.UUID
    psychologist_id: uuid.UUID
    student_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class PsychologistAssignmentListResponse(BaseModel):
    items: list[PsychologistAssignmentItem]
    total: int
    page: int
    limit: int
