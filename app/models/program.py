import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, Computed, DateTime, ForeignKey, Numeric, String, Table, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# M2M link between a specialty and the profession(s) it actually prepares
# someone for (see scripts/specialty_profession_map.py for how it's
# populated). Replaces the old `Program.profession_slugs` JSONB array —
# see migration that dropped it for why a real FK-backed table instead of
# a JSON array of Direction.slug strings.
program_directions = Table(
    "program_directions",
    Base.metadata,
    Column("program_id", UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), primary_key=True),
    Column("direction_id", UUID(as_uuid=True), ForeignKey("directions.id", ondelete="CASCADE"), primary_key=True),
)


class Program(Base):
    __tablename__ = "programs"
    __table_args__ = (
        UniqueConstraint("university_id", "name_normalized", name="uq_programs_university_name_normalized"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    university_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("universities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # DB-generated, kept in sync automatically on every insert/update — no
    # seed script needs to remember to set it. Strips only degree-level/track
    # labels ("(бакалавр)", "(бакалавр, BBA)", "(магистратура)",
    # "(практический психолог)"), NOT all parenthetical text: many suffixes
    # are real distinct specializations (e.g. "Переводческое дело (восточные
    # языки)" vs "(западные языки)") and must stay distinguishable. Backing
    # the (university_id, name_normalized) unique index — see
    # scripts/merge_duplicate_programs.py for the one-time cleanup this
    # required before the index could be added (6 pre-existing duplicate
    # pairs, same normalization rule).
    name_normalized: Mapped[str] = mapped_column(
        Text,
        Computed(
            # `\:` (not `:`) before "бакалавр" is deliberate — SQLAlchemy's
            # DDL text compiler otherwise reads ":бакалавр" as a named bind
            # parameter (Cyrillic counts as a word char), finds nothing bound
            # to it, and silently renders NULL in its place there — a real
            # rendering footgun, not a typo. Confirmed by the first attempt
            # at this migration literally shipping "(?NULL(?:..." to Postgres.
            "lower(trim(regexp_replace("
            "name, '\\s*\\((?\\:бакалавр(?:,\\s*[^)]*)?|магистратура|практический психолог)\\)\\s*', '', 'gi'"
            ")))",
            persisted=True,
        ),
        nullable=False,
    )
    # Direction rows this specialty prepares someone for, via the
    # program_directions FK table above — hand-mapped by
    # scripts/specialty_profession_map.py at seed time.
    directions: Mapped[list["Direction"]] = relationship(
        "Direction", secondary=program_directions, lazy="selectin", order_by="Direction.slug"
    )
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    # Raw subject-taxonomy tag from an external source (e.g. jinaq's
    # `major.category`: "ENGINEERING", "LAW", ...) — kept separate from
    # `directions` (RIASEC/Holland-code career matching, hand-mapped per
    # scripts/specialty_profession_map.py) since the two taxonomies don't
    # correspond 1:1 and this project never auto-derives one from the other.
    source_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cost_per_year: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # Free-text fallback for when cost is a range/mixed currency and doesn't
    # fit a single Decimal (e.g. "2 000 – 6 000 EUR в семестр для граждан вне
    # ЕС") — same pattern as University.ranking_label next to
    # University.ranking. UI shows cost_per_year when set, else this.
    cost_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Numeric range parsed out of cost_label/cost_text (scripts/parse_cost_label.py)
    # where the text states exactly one unambiguous annual figure — most of
    # this dataset's cost_label text has a second, different number for
    # something else (living costs, another program level, a currency
    # conversion note), so a conservative regex leaves those None rather than
    # guess. For KZT programs where the exact `cost_per_year` above is
    # already set, min/max/currency mirror it (min=max=cost_per_year, KZT)
    # so the frontend has one field set to sort/filter on regardless of
    # source. See docs/university-module-fix-plan.md A6.
    cost_per_year_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    cost_per_year_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    cost_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    who_its_for: Mapped[str | None] = mapped_column(Text, nullable=True)
    # KZ-501: {"kk": "..."} per-locale overrides of `description` / `who_its_for`
    # (both base columns hold the `ru` text). Nullable, filled incrementally by
    # KZ-504; the read side falls back to the base column when the locale key is
    # absent, so an empty map changes no response.
    description_i18n: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    who_its_for_i18n: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Legacy field from an early data pass — populated for only ~9 of 2442
    # programs. Display-only (shown on the program detail page when
    # non-empty), never used in matching/scoring. Don't add new logic that
    # relies on this being populated.
    career_options: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    requirements: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    deadlines: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    grants: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Row-level fallback source — set once when the row was first created,
    # rarely reflects any one field's actual origin once a row has been
    # touched by more than one seed/backfill script (nearly every row here
    # has, by now — KZ scrape + apply_grant_admission_data_2026.py +
    # apply_program_requirements_content_2027.py all write into the same
    # `requirements` dict). `fact_sources` below is the real per-field
    # answer; keep this only for rows nothing more specific has touched yet.
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Per-fact provenance: {field_path: {"url": str, "checked_at": "YYYY-MM-DD"}},
    # e.g. {"requirements.admission_scores_2026": {"url": "https://...",
    # "checked_at": "2026-08-19"}, "cost_label": {...}}. field_path uses dots
    # into `requirements`/`deadlines` for facts nested there, or a bare
    # top-level column name (e.g. "cost_label", "description"). Was flagged
    # "critical" in docs/university-data-research-brief.md section 5 as
    # blocking any further research from having anywhere honest to record
    # where/when a fact was checked — without it, "show the source" in the UI
    # (docs/university-module-fix-plan.md C5) can only ever be a per-row
    # guess, not a per-field answer. Absence of a key means "unknown source",
    # not "unverified" — most current facts predate this column and won't
    # have an entry; only write here going forward.
    fact_sources: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Top-level column names an admin has explicitly PATCHed at least once via
    # /admin/programs/{id} — see University.admin_locked_fields for the full
    # rationale (same mechanism, same docs/admin-edit-lock-plan.md).
    admin_locked_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    university: Mapped["University"] = relationship("University", back_populates="programs")

    @property
    def profession_slugs(self) -> list[str]:
        """Read-only view of `directions` as slugs — kept so existing callers
        (schemas, roadmap_builder, direction_service) that only need the
        slug strings don't have to touch the relationship directly. Assign
        `.directions` (a list of `Direction` rows) to change the mapping,
        not this property."""
        return [d.slug for d in self.directions]
