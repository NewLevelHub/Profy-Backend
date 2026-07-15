import uuid

from pydantic import BaseModel


class DirectionBase(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str

    model_config = {"from_attributes": True}


class DirectionDetail(DirectionBase):
    required_scores: dict[str, float] | None = None
    professions: list[str]
    skills_needed: list[str]
    subjects_to_develop: list[str]
    first_steps: list[str]
