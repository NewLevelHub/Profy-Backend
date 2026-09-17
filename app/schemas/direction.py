import uuid

from pydantic import BaseModel


class DirectionBase(BaseModel):
    """Locale already resolved by the service layer (`direction_service`) —
    `Direction.name` etc. are `{"ru": ..., "kk": ...}` maps on the ORM row, so
    these schemas are built explicitly (`pick_locale(...)`), never via a bare
    `model_validate(direction)` (`from_attributes` would just hand back the
    raw dict)."""

    id: uuid.UUID
    name: str
    slug: str
    holland_code: str


class DirectionDetail(DirectionBase):
    description: str
    professions: list[str]
    skills_needed: list[str]
    subjects_to_develop: list[str]
    first_steps: list[str]
