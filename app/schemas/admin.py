import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.artifact import ArtifactItem
from app.schemas.profile import ProfileResponse


# ---------------------------------------------------------------------------
# User list / detail
# ---------------------------------------------------------------------------

class AdminUserListItem(BaseModel):
    id: uuid.UUID
    email: str
    is_verified: bool
    is_active: bool
    is_admin: bool
    created_at: datetime
    has_profile: bool
    profile_name: str | None = None
    assessments_count: int = 0
    latest_assessment_status: str | None = None


class AdminUserListResponse(BaseModel):
    items: list[AdminUserListItem]
    total: int
    page: int
    limit: int


class AdminAssessmentSummary(BaseModel):
    id: uuid.UUID
    goal: str
    status: str
    current_block: int
    selected_direction_slug: str | None = None
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
    profile: ProfileResponse | None = None
    artifacts: list[ArtifactItem] = []
    assessments: list[AdminAssessmentSummary] = []


# ---------------------------------------------------------------------------
# Assessment detail — Akinator sub-schemas
# ---------------------------------------------------------------------------

class AkinatorAnswerItem(BaseModel):
    step: int
    question_text: str
    # None when selected_option_index was None ("не знаю")
    selected_answer: str | None
    # Belief snapshot immediately after this answer: slug → probability
    belief_after: dict[str, Any]


class TopDirectionItem(BaseModel):
    slug: str
    name: str | None = None
    probability: float


class AkinatorSessionSummary(BaseModel):
    status: str
    step: int
    top_directions: list[TopDirectionItem]
    rejected_leaves: list[str]
    liked: bool | None
    feedback_note: str | None
    feedback_at: datetime | None
    answers: list[AkinatorAnswerItem]


class ProfessionSimulationItem(BaseModel):
    leaf_slug: str
    leaf_name: str | None = None
    accepted: bool
    answers: list[Any]


class SubjectScoreItem(BaseModel):
    subject: str
    level: float | None
    interest: float | None
    is_strength: bool | None


class SubjectReadinessItem(BaseModel):
    direction_slug: str
    direction_name: str | None = None
    status: str
    subject_scores: list[SubjectScoreItem]


class DirectionRoadmapItem(BaseModel):
    direction_slug: str
    direction_name: str | None = None
    profession_options: list[Any]
    subjects_now: list[Any]
    starter_actions: list[Any]
    growth_focus: dict[str, Any]
    skills_to_build: list[Any]
    university_requirements: list[Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Assessment detail response
# ---------------------------------------------------------------------------

class AdminAssessmentDetailResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    profile_name: str | None = None
    goal: str
    status: str
    current_block: int
    selected_direction_slug: str | None = None
    selected_direction_name: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    # Akinator engine data
    akinator_session: AkinatorSessionSummary | None = None
    # Profession simulation logs for this assessment
    profession_simulations: list[ProfessionSimulationItem] = []
    # Subject readiness (post-direction confirmation)
    subject_readiness: SubjectReadinessItem | None = None
    # Direction roadmaps generated for this assessment
    roadmaps: list[DirectionRoadmapItem] = []
    # Deprecated — kept for backwards compat; always empty now
    responses: list[Any] = []


class AdminListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)
    search: str | None = None


class AdminFeedbackListItem(BaseModel):
    id: uuid.UUID
    user_email: str
    context: str
    rating: str
    message: str | None = None
    direction_slug: str | None = None
    created_at: datetime


class AdminFeedbackListResponse(BaseModel):
    items: list[AdminFeedbackListItem]
    total: int
    page: int
    limit: int
