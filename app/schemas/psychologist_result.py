"""Schemas for psychologist review of a student's report before it is
published (docs/psychologist-review-gate-plan.md §3).

Unlike the student-facing `result_v2` schemas, the detail response exposes
the stored raw/narrative fields (`big_five`, `thinking_style`, `careers`
with scores) — the psychologist needs them to judge the report.
"""


import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.i18n.catalog import key as i18n_key
from app.models.analysis_result import ReviewStatus
from app.schemas.student_strengths import StrengthBasis

# Mirrors `result_v2._MAX_CAREERS` — the student schema rejects more.
_MAX_CAREERS = 10


class PsychologistReviewQueueItem(BaseModel):
    assessment_id: uuid.UUID
    student_id: uuid.UUID
    student_name: str | None = None
    student_email: str
    age: int | None = None
    grade: int | None = None
    goal: str
    generated_at: datetime
    reviewed_at: datetime | None = None


class PsychologistReviewEditItem(BaseModel):
    """One saved edit of a report under review — `changed_fields` is
    `{"field": {"old": ..., "new": ...}}` for the fields that edit changed."""

    id: uuid.UUID
    edited_at: datetime
    editor_id: uuid.UUID | None = None
    editor_email: str | None = None
    changed_fields: dict[str, dict[str, Any]]


class ReviewTextCard(BaseModel):
    title: str
    description: str


class ReviewStrengthCard(ReviewTextCard):
    # PRO-432 — how the card is grounded; absent on a card the psychologist
    # added by hand.
    basis: StrengthBasis | None = None


class PsychologistResultDetailResponse(BaseModel):
    assessment_id: uuid.UUID
    review_status: ReviewStatus
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    published_by: uuid.UUID | None = None
    published_at: datetime | None = None
    summary: str
    careers: list[dict]
    strengths: list[str]
    weaknesses: list[str]
    development_plan: dict
    big_five: dict[str, float]
    thinking_style: dict[str, float]
    strength_cards: list[ReviewStrengthCard]
    thinking_style_notes: list[ReviewTextCard]
    final_analysis: str
    personality_notes: dict[str, str]
    motivation_highlights: list[str]
    created_at: datetime
    # The strength cards were built from earlier Belbin/АСТУР results than
    # the student's current ones (a retake after the report) — rebuild them
    # or publish as they are (PRO-432).
    strengths_stale: bool = False

    model_config = {"from_attributes": True}


class ReviewTextCardPatch(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    model_config = {"extra": "forbid"}


class ReviewStrengthCardPatch(ReviewTextCardPatch):
    basis: StrengthBasis | None = None


class ReviewCareerPatch(BaseModel):
    """Same shape `report_service._career_dict` stores — the student report
    is rebuilt from these keys, so an edited career must keep all of them.

    `match_score` is a float in [0, 1] (Pearson / normalized code match after
    PRO-385). It used to be an int 0–100; keeping `int` here 422'd every
    careers PATCH once the scorer started writing fractional scores
    (PRO-415 — reorder → save → publish)."""

    slug: str = Field(min_length=1)
    name: str = Field(min_length=1)
    holland_code: str
    match_score: float
    description: str
    professions: list[str]
    skills_needed: list[str]
    subjects_to_develop: list[str]
    first_steps: list[str]
    model_config = {"extra": "forbid"}


class PsychologistResultPatch(BaseModel):
    """Partial edit — only the fields sent are applied. Raw inputs other
    pipelines depend on (`profile`, `code`, `meta`, `report_version`) are
    deliberately not editable."""

    summary: str | None = Field(default=None, min_length=1)
    careers: list[ReviewCareerPatch] | None = Field(default=None, max_length=_MAX_CAREERS)
    strengths: list[str] | None = None
    weaknesses: list[str] | None = None
    strength_cards: list[ReviewStrengthCardPatch] | None = None
    thinking_style_notes: list[ReviewTextCardPatch] | None = None
    final_analysis: str | None = Field(default=None, min_length=1)
    personality_notes: dict[str, str] | None = None
    motivation_highlights: list[str] | None = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _no_explicit_nulls(self) -> "PsychologistResultPatch":
        # Omitting a field means "leave as is"; null would wipe a NOT NULL column.
        nulls = sorted(name for name in self.model_fields_set if getattr(self, name) is None)
        if nulls:
            raise ValueError(i18n_key("api_errors", "null_fields", locale="ru").format(fields=', '.join(nulls)))
        return self
