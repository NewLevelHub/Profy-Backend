import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.akinator_session import RevealLeaf


class ResultAxisHighlight(BaseModel):
    code: str
    label_ru: str
    direction_value: int


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
    created_at: datetime
