import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, model_validator

from app.schemas.roadmap import UniversityRequirement

# Shared by ProgramBrief/ProgramDetail's convert_cost_to_usd — units of
# foreign currency per 1 USD. Kept as one module-level constant instead of
# two copies so a rate update (or a newly-needed currency, like NZD/INR
# added for the foreign-university cost cleanup pass, see
# university-cards-ux-fix-plan.md §2/§10) only has to happen once.
CURRENCY_RATES_PER_USD: dict[str, float] = {
    "KZT": 480.0,
    "EUR": 0.92,
    "GBP": 0.77,
    "CNY": 7.15,
    "CAD": 1.37,
    "SGD": 1.35,
    "HKD": 7.80,
    "KRW": 1330.0,
    "AUD": 1.50,
    "SEK": 10.50,
    "NOK": 10.70,
    "CHF": 0.88,
    "JPY": 147.0,
    "ZAR": 18.0,
    "BRL": 5.50,
    "NZD": 1.65,
    "INR": 84.0,
    "USD": 1.0,
}


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
    description: str | None = None
    # Reads University.image_url — a computed property (see that model),
    # never a stored column, so a storage/CDN vendor swap never needs a DB
    # backfill.
    image_url: str | None = None
    # Whether the *requesting* user starred this university (PRO-265). Not an
    # ORM column and not derivable from the University row alone — the
    # service fills it in after model_validate, per caller, and it stays
    # False for anonymous callers.
    is_favorite: bool = False

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
    cost_currency: str | None = None
    cost_per_year_min: Decimal | None = None
    cost_per_year_max: Decimal | None = None

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def convert_cost_to_usd(self) -> "ProgramBrief":
        if self.cost_currency and (self.cost_per_year is not None or self.cost_per_year_min is not None):
            base_cost = self.cost_per_year
            if self.cost_per_year_min is not None and self.cost_per_year_max is not None:
                base_cost = (self.cost_per_year_min + self.cost_per_year_max) / 2
            
            if base_cost is not None:
                rate = CURRENCY_RATES_PER_USD.get(self.cost_currency.upper(), 1.0)
                usd_cost = float(base_cost) / rate
                self.cost_per_year = Decimal(str(round(usd_cost)))
        return self


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
    cost_currency: str | None = None
    cost_per_year_min: Decimal | None = None
    cost_per_year_max: Decimal | None = None

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def convert_cost_to_usd(self) -> "ProgramDetail":
        if self.cost_currency and (self.cost_per_year is not None or self.cost_per_year_min is not None):
            base_cost = self.cost_per_year
            if self.cost_per_year_min is not None and self.cost_per_year_max is not None:
                base_cost = (self.cost_per_year_min + self.cost_per_year_max) / 2
            
            if base_cost is not None:
                rate = CURRENCY_RATES_PER_USD.get(self.cost_currency.upper(), 1.0)
                usd_cost = float(base_cost) / rate
                self.cost_per_year = Decimal(str(round(usd_cost)))
        return self


class UniversityListItem(UniversityBrief):
    """A catalogue row. `programs_count` is the aggregate the list query
    already computes — a university with zero programs can be recommended to
    nobody, so the number is worth showing rather than hiding."""

    programs_count: int = 0


class UniversityListResponse(BaseModel):
    """Same {items, total, page, limit} envelope the admin lists use. The
    other public list endpoints return a bare array with no total, which is
    exactly why they can't be paginated — this one is not repeating that."""

    items: list[UniversityListItem]
    total: int
    page: int
    limit: int


class UniversityCountry(BaseModel):
    """One entry of the catalogue's country filter, with how many
    universities sit behind it — a filter with nothing behind it is worse
    than no filter."""

    country: str
    count: int


class UniversityDetail(UniversityBrief):
    """The university's own page. Deliberately does NOT expose
    `fact_sources`, `admin_locked_fields`, `ovpo_code` or `slug` — those are
    editorial/admin plumbing, not student-facing facts."""

    contacts: dict
    facilities: dict
    source_url: str | None = None
    programs: list[ProgramBrief] = []
