import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class UniversityBrief(BaseModel):
    id: uuid.UUID
    name: str
    country: str
    city: str
    website: str | None
    ranking: int | None

    model_config = {"from_attributes": True}


class ProgramBrief(BaseModel):
    id: uuid.UUID
    name: str
    profession_slugs: list[str]
    language: str
    cost_per_year: Decimal | None
    description: str | None
    university: UniversityBrief

    model_config = {"from_attributes": True}


class ProgramDetail(BaseModel):
    id: uuid.UUID
    name: str
    profession_slugs: list[str]
    language: str
    cost_per_year: Decimal | None
    description: str | None
    who_its_for: str | None
    career_options: list[str]
    requirements: dict
    deadlines: dict
    grants: list[dict]
    created_at: datetime
    university: UniversityBrief

    model_config = {"from_attributes": True}
