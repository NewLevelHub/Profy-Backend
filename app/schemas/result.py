import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.akinator_session import RevealLeaf
from app.schemas.university import UniversityBrief


class ResultProgramRecommendation(BaseModel):
    id: uuid.UUID
    name: str
    direction_slug: str
    language: str
    cost_per_year: float | None
    description: str | None
    university: UniversityBrief

    model_config = {"from_attributes": True}


class AxisGrowthExplanation(BaseModel):
    """Static, non-personalized copy for a growth-area axis — see
    app.core.axes.AXIS_GROWTH_COPY. Same text for every student/direction
    that surfaces this axis as a growth point."""
    meaning: str
    suggestion: str


class AxisComparisonItem(BaseModel):
    """One axis compared between the child's own normalized signal (see
    result_service._child_axis_scores) and the target direction's needs —
    "match" if the child's signal meets the need, "growth" if it falls
    short. `profile_value` is only set when the axis is actually one the
    direction needs (Direction.profile > 0); it's None for items surfaced
    through the whole-session fallback (see AkinatorResultResponse.
    is_direction_specific) — those aren't filtered by this direction at all,
    so a profile value would misleadingly imply they were. Exactly one of
    `strength_phrase` (match) / `explanation` (growth) is set, matching
    which side the item is on."""
    code: str
    label_ru: str
    profile_value: int | None = None
    child_score: float
    strength_phrase: str | None = None
    explanation: AxisGrowthExplanation | None = None


class AkinatorResultResponse(BaseModel):
    assessment_id: uuid.UUID
    direction_slug: str
    direction_name: str
    direction_description: str
    professions: list[str] = Field(default_factory=list)
    message: str
    matches: list[AxisComparisonItem]
    growth_areas: list[AxisComparisonItem]
    # False when no axis the direction actually needs had any real signal
    # from the child's answers — matches/growth_areas then fall back to the
    # child's strongest/weakest axes across the whole session, unfiltered by
    # this direction's profile (see result_service._axis_comparison_for).
    # The UI must say so rather than imply these are direction-specific.
    is_direction_specific: bool
    backups: list[RevealLeaf]
    recommended_programs: list[ResultProgramRecommendation]
    created_at: datetime
