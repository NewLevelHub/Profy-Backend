import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class AdminUniversityListItem(BaseModel):
    id: uuid.UUID
    name: str
    city: str
    country: str
    ranking: int | None
    uniranks_kz_rank: int | None
    uniranks_note: str | None
    updated_at: datetime | None
    programs_count: int

    model_config = {"from_attributes": True}


class AdminUniversityListResponse(BaseModel):
    items: list[AdminUniversityListItem]
    total: int
    page: int
    limit: int

    model_config = {"from_attributes": True}


class AdminProgramBrief(BaseModel):
    id: uuid.UUID
    name: str
    language: str
    cost_per_year: Decimal | None
    cost_label: str | None

    model_config = {"from_attributes": True}


class AdminUniversityDetail(BaseModel):
    id: uuid.UUID
    name: str
    slug: str | None
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
    description: str | None
    created_at: datetime
    updated_at: datetime | None
    source_url: str | None
    programs: list[AdminProgramBrief]
    admin_locked_fields: list[str]

    model_config = {"from_attributes": True}


class AdminUniversityUpdateRequest(BaseModel):
    name: str | None = None
    short_name: str | None = None
    aliases: list[str] | None = None
    location: str | None = None
    website: str | None = None
    ranking: int | None = None
    ranking_label: str | None = None
    uniranks_kz_rank: int | None = None
    uniranks_world_rank: int | None = None
    uniranks_note: str | None = None
    description: str | None = None
    city: str | None = None
    country: str | None = None
    source_url: str | None = None


class AdminUniversityBrief(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class AdminProgramDetail(BaseModel):
    id: uuid.UUID
    university_id: uuid.UUID
    name: str
    language: str
    cost_per_year: Decimal | None
    cost_label: str | None
    description: str | None
    who_its_for: str | None
    requirements: dict
    deadlines: dict
    grants: list
    created_at: datetime
    updated_at: datetime | None
    source_url: str | None
    university: AdminUniversityBrief
    admin_locked_fields: list[str]

    model_config = {"from_attributes": True}


class AdminProgramUpdateRequest(BaseModel):
    name: str | None = None
    language: str | None = None
    cost_per_year: Decimal | None = None
    cost_label: str | None = None
    description: str | None = None
    who_its_for: str | None = None
    requirements: dict | None = None
    deadlines: dict | None = None
    grants: list | None = None
    source_url: str | None = None
