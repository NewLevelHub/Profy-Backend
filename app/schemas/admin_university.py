import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel

from app.schemas.roadmap import ProgramGrant


class AdminProgramGrant(ProgramGrant):
    """One grant/scholarship entry of `Program.grants`.

    The shape was undocumented and untyped, so the admin edited grants as raw
    JSON in a textarea: one typo and the save failed, or worse, saved a
    structure nothing downstream could read. It is the same `ProgramGrant`
    the roadmap already builds from these rows — `name` plus optional
    `amount`/`conditions` — which is what all 1309 programs carrying grants
    actually hold today (every live entry has `name` and nothing else).

    Extra keys are preserved rather than dropped: a read-edit-write round trip
    through the admin must not silently delete a field some importer added
    that this schema has not learned about yet.
    """

    model_config = {"extra": "allow"}


class AdminUniversityListItem(BaseModel):
    """`ranking` alone is not comparable across rows — one Integer column
    holds a QS world position, a national tier and a field-specific rank at
    once (see University.ranking). `ranking_label` is the string the source
    actually gave ("#28 (QS World)", "Top-20 (Нац. рейтинг)"), and is the only
    honest thing to show next to the number in a list."""

    id: uuid.UUID
    name: str
    city: str
    country: str
    ranking: int | None
    ranking_label: str | None
    uniranks_kz_rank: int | None
    uniranks_note: str | None
    updated_at: datetime | None
    programs_count: int

    model_config = {"from_attributes": True}


class AdminUniversityCountry(BaseModel):
    """One entry of the country filter's option list. Counts come with it so
    the picker can say how much each option actually covers."""

    country: str
    universities_count: int


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
    """`requirements` and `deadlines` stay open dicts because several
    importers write into the same two columns, but the keys that legally
    appear in `requirements` are these — the second half of
    docs/admin-backend-requests-pro-242.md §8, which asked for exactly this
    list so a save cannot quietly drop one:

    ``exams``           list[str]  — entrance exams / subject pairs
    ``notes``           list[str]  — free-text admission notes (on every row)
    ``min_ent_threshold`` int      — state-grant eligibility bar (ЕНТ)
    ``min_ent``         int        — older name for the same bar
    ``min_ent_paid``    int        — bar for the paid track
    ``admission_scores_2026`` list — real grant-winning scores, disjoint from
                                     ``min_ent_threshold`` by seed source
    ``grant_scores``    dict       — per-category grant scores
    ``grants_allocated_count`` int
    ``min_gpa`` float, ``min_sat`` int, ``min_ielts`` float
    ``needs_essay`` / ``needs_recommendations`` / ``needs_interview`` bool
    ``needs_portfolio`` bool
    ``source_required_documents`` list[str]
    ``extracurriculars`` list[str]
    ``duration_years`` int, ``has_dual_degree`` bool
    ``cost_label`` str

    Live data currently uses only ``notes`` (2437 programs), ``exams`` and
    ``min_ent_threshold`` (~1220 each) and ``admission_scores_2026`` (118);
    the rest are read by app/services/university_requirements.py and written
    by the scripts/apply_*.py importers. `deadlines` is empty on every row
    today. Both are saved as a whole-object replace, so an editing form must
    merge into the original rather than send only the keys it knows.
    """

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
    grants: list[AdminProgramGrant]
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
    grants: list[AdminProgramGrant] | None = None
    source_url: str | None = None
