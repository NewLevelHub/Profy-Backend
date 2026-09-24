"""Schemas for the psychologist-facing student views (PRO-327 / Milestone 2).

Deliberately separate from `AdminUserDetailResponse` — psychologists reuse
`admin_service.get_user_detail()` for the data fetch, but the API contract
must not expose the admin schema type directly.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.artifact import ArtifactItem
from app.schemas.new_tests import (
    AspirationLevelSection,
    EmpathyConfidenceSection,
    IntelligenceSection,
    NewTestsSections,
    ProfessionalTypesSection,
    TeamRoleSection,
    TemperamentSection,
)
from app.schemas.profile import ProfileResponse
from app.schemas.psych_ai_analysis import PsychAiAnalysisOutput
from app.schemas.result_v2 import PsychoEmotionalSection, ResultV2Schema


class PsychologistStudentListItem(BaseModel):
    id: uuid.UUID
    email: str
    profile_name: str | None = None
    age_group: str | None = None
    assigned_at: datetime


class PsychologistAvailableStudentItem(BaseModel):
    """Student not yet claimed by this psychologist (PRO-337 selection flow)."""

    id: uuid.UUID
    email: str
    profile_name: str | None = None
    age_group: str | None = None
    has_pending_review: bool = False


class PsychologistAssessmentSummary(BaseModel):
    id: uuid.UUID
    goal: str
    status: str
    answered_count: int
    total_questions: int
    created_at: datetime
    completed_at: datetime | None = None
    has_result: bool = False
    # "pending_review" | "published", None when there is no result yet.
    review_status: str | None = None


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


class PsychologistTestResultsResponse(BaseModel):
    """Pure test-results surface for one assessment: the 7 instruments
    (ДДО/способности, Белбин, Айзенк, АСТУР, Элерс, Бойко+Кондаш, МЦВ
    Собчик) and nothing else — no narrative/RIASEC content from the
    student-facing report, unlike `PsychologistReportResponse.report`.

    Reuses `NewTestsSections`' 6 fields as-is (same builder,
    `new_tests_report_service.build_new_tests_sections`) plus
    `psychoemotional`, which otherwise only exists bolted onto the RIASEC
    report object via `report_service.psych_sections_for` — folded in here
    so all 7 tests live in one flat, narrative-free payload."""

    professional_types: ProfessionalTypesSection | None = None
    team_role: TeamRoleSection | None = None
    temperament: TemperamentSection | None = None
    intelligence: IntelligenceSection | None = None
    aspiration_level: AspirationLevelSection | None = None
    empathy_confidence: EmpathyConfidenceSection | None = None
    psychoemotional: PsychoEmotionalSection | None = None
    model_config = {"extra": "forbid"}
