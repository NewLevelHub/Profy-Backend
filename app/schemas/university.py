import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.roadmap import UniversityRequirement


class UniversityBrief(BaseModel):
    id: uuid.UUID
    name: str
    short_name: str | None
    aliases: list[str]
    location: str | None
    country: str
    city: str
    website: str | None
    ranking: int | None
    ranking_label: str | None
    uniranks_kz_rank: int | None
    uniranks_world_rank: int | None
    uniranks_note: str | None

    model_config = {"from_attributes": True}


class ProgramBrief(BaseModel):
    id: uuid.UUID
    name: str
    profession_slugs: list[str]
    language: str
    cost_per_year: Decimal | None
    # Free-text fallback for when cost is a range/mixed currency — see
    # Program.cost_label. UI shows cost_per_year when set, else this.
    cost_label: str | None
    description: str | None
    university: UniversityBrief

    model_config = {"from_attributes": True}


class ProgramDetail(BaseModel):
    id: uuid.UUID
    name: str
    profession_slugs: list[str]
    language: str
    cost_per_year: Decimal | None
    cost_label: str | None
    description: str | None
    who_its_for: str | None
    career_options: list[str]
    # Raw, kept for backward compatibility / debugging — the frontend should
    # render from `requirements_summary` below, not this. Two different seed
    # batches use two different key shapes here (see
    # app/services/university_requirements.py), which is exactly why a raw
    # key-value dump of this field reads as inconsistent garbage on the page.
    requirements: dict
    deadlines: dict
    grants: list[dict]
    created_at: datetime
    university: UniversityBrief
    # Same clean, typed facts the direction-roadmap prompt uses
    # (app/services/university_requirements.py) — single source of truth for
    # "what does this program actually require", rendered consistently
    # wherever a program's requirements are shown.
    requirements_summary: UniversityRequirement

    model_config = {"from_attributes": True}
