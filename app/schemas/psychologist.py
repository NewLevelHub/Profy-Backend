"""Schemas for the psychologist-facing student views (PRO-327 / Milestone 2).

Deliberately separate from `AdminUserDetailResponse` — psychologists reuse
`admin_service.get_user_detail()` for the data fetch, but the API contract
must not expose the admin schema type directly.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.artifact import ArtifactItem
from app.schemas.new_tests import NewTestsSections
from app.schemas.profile import ProfileResponse
from app.schemas.psych_ai_analysis import PsychAiAnalysisOutput
from app.schemas.result_v2 import ResultV2Schema


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


class PsychologistReportResponse(BaseModel):
    """PRO-338 Ф0.3 — the specialist-only report surface for one assessment:
    the same student-facing report shape (`report`, reused as-is from
    result_v2.py, not duplicated field-by-field) plus the 6 new-tests
    sections (`new_tests`, reused as-is from new_tests.py) that never reach
    the student's own /result.

    `ai_analysis` — per-block AI commentary + a final synthesis + one
    profession picked from `report.careers` (never invented, see
    app/services/psych_ai_analysis_validator.py). Lazily generated on first
    view and cached on AnalysisResult.psych_ai_analysis; `None` when the LLM
    is disabled, generation failed after retries, or there's no data yet to
    analyze — the psychologist sees "not available", never a fabricated
    analysis standing in for a real one."""

    report: ResultV2Schema
    new_tests: NewTestsSections
    ai_analysis: PsychAiAnalysisOutput | None = None
    model_config = {"extra": "forbid"}
