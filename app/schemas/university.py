import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, model_validator

from app.i18n import DEFAULT_LOCALE


class ProgramGrant(BaseModel):
    name: str
    amount: str | None = None
    conditions: str | None = None


class UniversityRequirement(BaseModel):
    """Backend-populated, per-program facts from `Program`/`University`, shown
    as `ProgramDetail.requirements_summary` on the program card.

    `None` means "no data for this field" — it is never used to mean "not
    required". `portfolio_needed=False` is a real, known fact and must stay
    distinguishable from "we don't know" (`None`).

    `min_ent_threshold`/`admission_scores_2026`/`notes` are disjoint by seed
    source (the 2026 grant-competition PDF pass): a program gets EITHER
    a `min_ent_threshold` (no 2026-2027 grant-competition data exists) OR
    `admission_scores_2026` entries (this year's real grant-winning scores),
    rarely both. Both represent the state grant-competition eligibility bar
    (MES RK reference data), not a generic "minimum to enrol at all" —
    labelled accordingly in the UI, not as a plain admission minimum.
    `notes` (subject-pair hints per specialty) can appear either way. All
    three were previously silently dropped by `_map_program_requirement`."""

    program_name: str
    university_name: str
    city: str
    country: str
    website: str | None = None
    # Actual language of instruction (Program.language, e.g. "Английский,
    # немецкий") — always set. Distinct from `language_level` below (a
    # required IELTS/TOEFL band), which is sparse/optional.
    program_language: str
    exams: list[str]
    # Set only when `exams` came back empty AND a general university note
    # keyword-matched this program's own name (see
    # university_requirements._note_hint_for_program) — an inferred hint, not
    # a confirmed per-program fact, and the frontend must label it as such.
    exam_hint_from_notes: str | None = None
    application_deadline: str | None = None
    grants: list[ProgramGrant] = []
    # Required IELTS/TOEFL band (requirements["min_ielts"]) — sparse/optional,
    # NOT the language of instruction (see `program_language` above).
    language_level: str | None = None
    portfolio_needed: bool | None = None
    required_documents: list[str] | None = None
    min_ent_threshold: int | None = None
    min_ent_paid: int | None = None
    min_gpa: float | None = None
    min_sat: int | None = None
    extracurriculars: list[str] = []
    admission_scores_2026: list[str] = []
    grant_scores: dict[str, str] = {}
    grants_allocated_count: int | None = None
    duration_years: float | None = None
    has_dual_degree: bool | None = None
    has_dormitory: bool | None = None
    dormitory_cost_label: str | None = None
    has_military_department: bool | None = None
    admissions_contacts: dict[str, str] = {}
    notes: list[str] = []
    # None (default) = "we haven't specifically researched this university's
    # ENT policy" — same as every other field here, absence isn't a claim.
    # False is a real, confirmed fact (e.g. Nazarbayev University, or a
    # foreign-funded branch campus like Astana MSU) — the frontend must show
    # "не требуется", never "не установлен", when this is False, since those
    # mean genuinely different things to an applicant. True is set for
    # confirmed ENT-requiring universities that also run their own
    # additional test (most KZ private universities), purely so the
    # frontend never has to guess from a missing value alone.
    requires_ent: bool | None = None


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
    # KZ-206 follow-up: "kk" when a Kazakh official name override exists for
    # this (Kazakhstan) university, "ru" otherwise. Same badge rule as
    # description_locale.
    name_locale: str = DEFAULT_LOCALE
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
    # KZ-501: locale actually served in `description` — "kk" when the kk
    # override exists, "ru" otherwise (fallback). The frontend shows a
    # "description only in Russian" note when this != the UI locale (KZ-502).
    description_locale: str = DEFAULT_LOCALE
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
    # "kk" when a Kazakh program-name override is served (Kazakhstan
    # universities), "ru" otherwise. Same badge rule as description_locale.
    name_locale: str = DEFAULT_LOCALE
    profession_slugs: list[str]
    language: str
    cost_per_year: Decimal | None
    # Free-text fallback for when cost is a range/mixed currency — see
    # Program.cost_label. UI shows cost_per_year when set, else this.
    cost_label: str | None
    description: str | None
    description_locale: str = DEFAULT_LOCALE
    university: UniversityBrief
    cost_currency: str | None = None
    cost_per_year_min: Decimal | None = None
    cost_per_year_max: Decimal | None = None

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def convert_cost_to_usd(self) -> "ProgramBrief":
        # Idempotent: FastAPI re-validates an already-built ProgramBrief on
        # response serialization. Without flipping the currency to USD after
        # the first pass, a second pass would divide the already-USD amount
        # by the original rate again (960000 KZT → 2000 → 4).
        if (
            self.cost_currency
            and self.cost_currency.upper() != "USD"
            and (self.cost_per_year is not None or self.cost_per_year_min is not None)
        ):
            base_cost = self.cost_per_year
            if self.cost_per_year_min is not None and self.cost_per_year_max is not None:
                base_cost = (self.cost_per_year_min + self.cost_per_year_max) / 2

            if base_cost is not None:
                rate = CURRENCY_RATES_PER_USD.get(self.cost_currency.upper(), 1.0)
                usd_cost = float(base_cost) / rate
                self.cost_per_year = Decimal(str(round(usd_cost)))
                self.cost_currency = "USD"
        return self


class ProgramDetail(BaseModel):
    id: uuid.UUID
    name: str
    name_locale: str = DEFAULT_LOCALE
    profession_slugs: list[str]
    language: str
    cost_per_year: Decimal | None
    cost_label: str | None
    description: str | None
    who_its_for: str | None
    # KZ-501: locale actually served in `description` / `who_its_for` — "ru"
    # unless a kk override for that field exists. Drives the KZ-502 note.
    description_locale: str = DEFAULT_LOCALE
    who_its_for_locale: str = DEFAULT_LOCALE
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
    # Clean, typed facts from app/services/university_requirements.py —
    # single source of truth for
    # "what does this program actually require", rendered consistently
    # wherever a program's requirements are shown.
    requirements_summary: UniversityRequirement
    cost_currency: str | None = None
    cost_per_year_min: Decimal | None = None
    cost_per_year_max: Decimal | None = None

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def convert_cost_to_usd(self) -> "ProgramDetail":
        # Same idempotency contract as ProgramBrief.convert_cost_to_usd —
        # see that docstring. Without it, response re-validation double-divides.
        if (
            self.cost_currency
            and self.cost_currency.upper() != "USD"
            and (self.cost_per_year is not None or self.cost_per_year_min is not None)
        ):
            base_cost = self.cost_per_year
            if self.cost_per_year_min is not None and self.cost_per_year_max is not None:
                base_cost = (self.cost_per_year_min + self.cost_per_year_max) / 2

            if base_cost is not None:
                rate = CURRENCY_RATES_PER_USD.get(self.cost_currency.upper(), 1.0)
                usd_cost = float(base_cost) / rate
                self.cost_per_year = Decimal(str(round(usd_cost)))
                self.cost_currency = "USD"
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
