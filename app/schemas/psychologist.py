"""Schemas for the psychologist-facing student views (PRO-327 / Milestone 2).

Deliberately separate from `AdminUserDetailResponse` — psychologists reuse
`admin_service.get_user_detail()` for the data fetch, but the API contract
must not expose the admin schema type directly.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.artifact import ArtifactItem
from app.schemas.profile import ProfileResponse


class PsychologistStudentListItem(BaseModel):
    id: uuid.UUID
    email: str
    profile_name: str | None = None
    age_group: str | None = None
    assigned_at: datetime


class PsychologistAssessmentSummary(BaseModel):
    id: uuid.UUID
    goal: str
    status: str
    answered_count: int
    total_questions: int
    created_at: datetime
    completed_at: datetime | None = None
    has_result: bool = False
    has_roadmap: bool = False


class PsychologistStudentDetailResponse(BaseModel):
    id: uuid.UUID
    email: str
    is_verified: bool
    is_active: bool
    created_at: datetime
    profile: ProfileResponse | None = None
    artifacts: list[ArtifactItem] = []
    assessments: list[PsychologistAssessmentSummary] = []


class PsychologistNoteCreate(BaseModel):
    content: str = Field(min_length=1)


class PsychologistNoteUpdate(BaseModel):
    content: str = Field(min_length=1)


class PsychologistNoteItem(BaseModel):
    id: uuid.UUID
    psychologist_id: uuid.UUID
    student_id: uuid.UUID
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}
