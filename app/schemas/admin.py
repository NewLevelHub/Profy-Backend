import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.artifact import ArtifactItem
from app.schemas.profile import ProfileResponse


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


class AdminResponseItem(BaseModel):
    question_id: uuid.UUID
    block: str
    question_text: str
    question_order: int
    selected_option_index: int
    selected_answer_text: str
    scores: dict[str, Any]
    created_at: datetime


class AdminAssessmentDetailResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    profile_name: str | None = None
    goal: str
    status: str
    current_block: int
    created_at: datetime
    completed_at: datetime | None = None
    responses: list[AdminResponseItem] = []
    analysis_result: dict | None = None
    roadmap: dict | None = None


class AdminListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)
    search: str | None = None
