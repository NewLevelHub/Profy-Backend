"""Schemas for psychologist review of a student's report before it is
published (docs/psychologist-review-gate-plan.md §3).

Unlike the student-facing `result_v2` schemas, the detail response exposes
the stored raw/narrative fields (`big_five`, `thinking_style`, `careers`
with scores) — the psychologist needs them to judge the report.
"""


import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.i18n.catalog import key as i18n_key
from app.models.analysis_result import ReviewStatus
from app.models.analysis_result_review_edit import ReviewEditSource
from app.schemas.student_strengths import StrengthBasis
from app.schemas.validation import (
    LIST_ITEM_MAX_LENGTH,
    LIST_MAX_ITEMS,
    LONG_TEXT_MAX_LENGTH,
    ListItemText,
    LongText,
)

# Mirrors `result_v2._MAX_CAREERS` — the student schema rejects more.
_MAX_CAREERS = 10
# A category code («R», «A», …) or a trait key — an identifier, not prose.
_Code = Annotated[str, Field(max_length=64)]


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
    source: ReviewEditSource = ReviewEditSource.psychologist
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
    # The strength cards were built under an older strength rules version
    # (app/data/student_strengths_rules.json) — rebuild them (PRO-432).
    strengths_stale: bool = False
    # The AI analysis's recommended profession (psych_ai_analysis), put first
    # in `careers` by default — None when there is no analysis yet.
    ai_recommended_slug: str | None = None
    # «Почему тебе подходит» the student reads under their best match while
    # `top_career_why_slug` is first in `careers` (AnalysisResult.top_career_why).
    top_career_why: str | None = None
    top_career_why_slug: str | None = None

    model_config = {"from_attributes": True}

    @field_validator("top_career_why", mode="before")
    @classmethod
    def _top_career_why_text(cls, value: Any) -> Any:
        # Stored as {"slug", "text"}; the slug goes to top_career_why_slug.
        return value.get("text") if isinstance(value, dict) else value


class ReviewTextCardPatch(BaseModel):
    title: str = Field(min_length=1, max_length=LIST_ITEM_MAX_LENGTH)
    description: str = Field(min_length=1, max_length=LONG_TEXT_MAX_LENGTH)
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

    slug: str = Field(min_length=1, max_length=100)  # `directions.slug` is varchar(100)
    name: str = Field(min_length=1, max_length=255)
    holland_code: _Code
    match_score: float
    description: LongText
    professions: list[ListItemText] = Field(max_length=LIST_MAX_ITEMS)
    skills_needed: list[ListItemText] = Field(max_length=LIST_MAX_ITEMS)
    subjects_to_develop: list[ListItemText] = Field(max_length=LIST_MAX_ITEMS)
    first_steps: list[ListItemText] = Field(max_length=LIST_MAX_ITEMS)
    model_config = {"extra": "forbid"}


class PsychologistResultPatch(BaseModel):
    """Partial edit — only the fields sent are applied. Raw inputs other
    pipelines depend on (`profile`, `code`, `meta`, `report_version`) are
    deliberately not editable."""

    summary: str | None = Field(default=None, min_length=1, max_length=LONG_TEXT_MAX_LENGTH)
    careers: list[ReviewCareerPatch] | None = Field(default=None, max_length=_MAX_CAREERS)
    strengths: list[_Code] | None = Field(default=None, max_length=LIST_MAX_ITEMS)
    weaknesses: list[_Code] | None = Field(default=None, max_length=LIST_MAX_ITEMS)
    strength_cards: list[ReviewStrengthCardPatch] | None = Field(default=None, max_length=LIST_MAX_ITEMS)
    thinking_style_notes: list[ReviewTextCardPatch] | None = Field(default=None, max_length=LIST_MAX_ITEMS)
    final_analysis: str | None = Field(default=None, min_length=1, max_length=LONG_TEXT_MAX_LENGTH)
    personality_notes: dict[_Code, LongText] | None = Field(default=None, max_length=LIST_MAX_ITEMS)
    motivation_highlights: list[LongText] | None = Field(default=None, max_length=LIST_MAX_ITEMS)
    # Text only — which career it belongs to is the AI analysis's pick.
    top_career_why: str | None = Field(default=None, min_length=1, max_length=LONG_TEXT_MAX_LENGTH)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _no_explicit_nulls(self) -> "PsychologistResultPatch":
        # Omitting a field means "leave as is"; null would wipe a NOT NULL column.
        nulls = sorted(name for name in self.model_fields_set if getattr(self, name) is None)
        if nulls:
            raise ValueError(i18n_key("api_errors", "null_fields", locale="ru").format(fields=', '.join(nulls)))
        return self
