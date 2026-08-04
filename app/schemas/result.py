import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CareerMatch(BaseModel):
    slug: str
    name: str
    holland_code: str
    match_score: int
    description: str
    professions: list[str]
    skills_needed: list[str]
    subjects_to_develop: list[str]
    first_steps: list[str]


class RiasecMeta(BaseModel):
    differentiation: float
    consistency: Literal["high", "medium", "low"]
    aversion: dict[str, int]


class DevelopmentPlan(BaseModel):
    reinforce: list[str]
    compensate: list[str]


class AnalysisResultResponse(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    profile: dict[str, float]
    code: list[str]
    meta: RiasecMeta
    careers: list[CareerMatch]
    strengths: list[str]
    weaknesses: list[str]
    development_plan: DevelopmentPlan
    summary: str
    created_at: datetime

    model_config = {"from_attributes": True}
