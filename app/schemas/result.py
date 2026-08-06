import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CareerMatch(BaseModel):
    slug: str
    name: str
    holland_code: str
    category_slugs: list[str]
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


class ThinkingStyle(BaseModel):
    creative_think: float
    systematic: float
    strategic: float
    practical: float


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
    big_five: dict[str, float]
    thinking_style: ThinkingStyle
    personality_highlights: list[str]
    personality_profile: dict[str, float]
    personality_notes: dict[str, str]
    motivation: dict[str, int]
    motivation_top: list[str]
    motivation_highlights: list[str]
    summary: str
    created_at: datetime

    model_config = {"from_attributes": True}
