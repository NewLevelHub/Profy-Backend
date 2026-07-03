import uuid
from datetime import datetime

from pydantic import BaseModel


class DirectionResult(BaseModel):
    slug: str
    name: str
    match_score: int
    why_it_fits: str
    description: str
    professions: list[str]
    skills_needed: list[str]
    subjects_to_develop: list[str]
    first_steps: list[str]


class AnalysisResultResponse(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    summary: str
    strengths: list[str]
    interests_map: dict[str, float]
    thinking_style: dict[str, float]
    motivation: list[str]
    directions: list[DirectionResult]
    wellbeing_zones: list[str] = []
    created_at: datetime

    model_config = {"from_attributes": True}
