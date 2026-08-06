import uuid

from pydantic import BaseModel


class DirectionBase(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    holland_code: str
    category_slugs: list[str]

    model_config = {"from_attributes": True}


class DirectionDetail(DirectionBase):
    description: str
    professions: list[str]
    skills_needed: list[str]
    subjects_to_develop: list[str]
    first_steps: list[str]
