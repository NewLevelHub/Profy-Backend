import uuid

from pydantic import BaseModel


class DirectionBase(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str
    is_leaf: bool = True
    parent_id: uuid.UUID | None = None
    label_junior: str | None = None
    # Concrete job titles this specialty leads to (Direction.professions) —
    # e.g. software-engineer -> ["Backend-разработчик", ...]. Empty for
    # section nodes. Included here (not just on DirectionDetail) so the
    # /directions/tree picker can search by job title, not only specialty name.
    professions: list[str] = []

    model_config = {"from_attributes": True}


class DirectionDetail(DirectionBase):
    required_scores: dict[str, float] | None = None
    skills_needed: list[str]
    subjects_to_develop: list[str]
    first_steps: list[str]


class DirectionTreeNode(BaseModel):
    """Section (sphere) with nested leaf professions for the known-profession picker."""

    id: uuid.UUID
    name: str
    slug: str
    description: str
    professions: list[DirectionBase]

    model_config = {"from_attributes": True}
