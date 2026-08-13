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


class AdminCareerMatch(BaseModel):
    slug: str
    name: str
    holland_code: str
    match_score: int
    description: str
    professions: list[str]
    skills_needed: list[str]
    subjects_to_develop: list[str]
    first_steps: list[str]


class AnalysisMeta(BaseModel):
    """Renamed from the old `RiasecMeta`: this shape is produced identically
    by riasec_service (middle/senior) and mi_service (junior) — it was never
    RIASEC-specific, only named as if it were."""

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
    student-facing API. `profile` and `code` hold MI category keys for
    junior assessments and RIASEC letters for middle/senior; nothing here
    (or in any consumer of this schema) should assume one or the other."""

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
    summary: str
    created_at: datetime

    model_config = {"from_attributes": True}
