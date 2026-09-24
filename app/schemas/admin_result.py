"""Admin-only raw result contract.

A standalone copy of the current `AnalysisResultResponse`
(app/schemas/result.py) — decoupled on purpose. Once the student-facing
schema is stripped down to a safe, non-numeric shape (see
docs/result-report-redesign-plan.md), this schema keeps returning the full
raw scores/codes to the admin panel unaffected. Nothing here is imported
from result.py, and nothing in result.py imports this — that's the whole
point of the split.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.analysis_result import ReviewStatus


class AdminCareerMatch(BaseModel):
    slug: str
    name: str
    holland_code: str
    match_score: float
    description: str
    professions: list[str]
    skills_needed: list[str]
    subjects_to_develop: list[str]
    first_steps: list[str]


class AnalysisMeta(BaseModel):
    """Renamed from the old `RiasecMeta`; produced by riasec_service."""

    differentiation: float
    consistency: Literal["high", "medium", "low"]
    aversion: dict[str, int]


class AdminDevelopmentPlan(BaseModel):
    reinforce: list[str]
    compensate: list[str]


class AdminThinkingStyle(BaseModel):
    creative_think: float
    systematic: float
    strategic: float
    practical: float


class AdminStrengthCard(BaseModel):
    title: str
    description: str


class AdminThinkingStyleNote(BaseModel):
    title: str
    description: str


class AdminAnalysisResultResponse(BaseModel):
    """Full raw analysis result — admin/internal only, never exposed to the
    student-facing API. `profile` and `code` hold RIASEC letters."""

    id: uuid.UUID
    assessment_id: uuid.UUID
    profile: dict[str, float]
    code: list[str]
    meta: AnalysisMeta
    careers: list[AdminCareerMatch]
    strengths: list[str]
    weaknesses: list[str]
    development_plan: AdminDevelopmentPlan
    big_five: dict[str, float]
    thinking_style: AdminThinkingStyle
    personality_highlights: list[str]
    personality_profile: dict[str, float]
    personality_notes: dict[str, str]
    motivation: dict[str, int]
    motivation_top: list[str]
    motivation_highlights: list[str]
    # v2 narrative fields — empty/`report_version=1` on every row until the
    # narrative-generation pipeline lands (docs/rs-progress-notes.md). A
    # legacy row is `report_version=1` explicitly, never inferred from
    # these lists happening to be empty.
    strength_cards: list[AdminStrengthCard]
    thinking_style_notes: list[AdminThinkingStyleNote]
    report_version: int
    # Psychologist review gate — admins see these unconditionally, their
    # access is never gated by review_status.
    review_status: ReviewStatus
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    published_by: uuid.UUID | None = None
    published_at: datetime | None = None
    summary: str
    created_at: datetime

    model_config = {"from_attributes": True}
