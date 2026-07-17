import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.akinator_session import RevealLeaf
from app.schemas.university import UniversityBrief


class ResultAxisHighlight(BaseModel):
    code: str
    label_ru: str
    direction_value: int


class ResultProgramRecommendation(BaseModel):
    id: uuid.UUID
    name: str
    direction_slug: str
    language: str
    cost_per_year: float | None
    description: str | None
    university: UniversityBrief

    model_config = {"from_attributes": True}


class ChildAxisSignal(BaseModel):
    """A summed axis score from the child's own answers across the whole
    session (see result_service._child_axis_totals) — distinct from
    ResultAxisHighlight, which describes the profession's own -2..2 axis
    profile, not what the child actually answered."""
    code: str
    label_ru: str
    score: float


class AkinatorResultResponse(BaseModel):
    assessment_id: uuid.UUID
    direction_slug: str
    direction_name: str
    direction_description: str
    message: str
    matched_axes: list[ResultAxisHighlight]
    strengths: list[ChildAxisSignal]
    growth_areas: list[ChildAxisSignal]
    backups: list[RevealLeaf]
    recommended_programs: list[ResultProgramRecommendation]
    created_at: datetime
