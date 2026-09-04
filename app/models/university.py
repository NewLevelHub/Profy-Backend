import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class University(Base):
    __tablename__ = "universities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Stable identifier from university-data/*.py — lets seed_kz_universities.py
    # upsert idempotently. Nullable because the older hand-written entries in
    # seed_universities.py predate this column; those get backfilled by slug
    # via the LEGACY_NAME_BY_SLUG alias map when seed_kz_universities.py runs.
    slug: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    # Canonical external ID from the Research Organization Registry (ror.org).
    # Populated for foreign universities looked up via scripts/find_ror_id.py
    # before they're added to a seed data file — lets seed scripts dedup on a
    # stable ID instead of `slug` (which is derived from name and drifts
    # across spelling variants of the same institution). See docs/university-module-fix-plan.md B1.
    ror_id: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True, index=True)
    # Official 3-digit code from the MES RK grant-competition registry
    # (scripts/data/ovpo_registry_2026.json, transcribed from the "Список
    # обладателей образовательных грантов" PDF appendix). Canonical
    # identifier for reconciling a University row against that PDF's
    # admission-score data — replaces fuzzy name matching (LEGACY_NAME_BY_SLUG),
    # which is why ~27 of 64 KZ universities never got grant-score data despite
    # the PDF actually covering them (see docs/ovpo-registry-gap-analysis.md).
    ovpo_code: Mapped[str | None] = mapped_column(String(10), nullable=True, unique=True, index=True)
    # Already present in university-data/*.py source records but previously
    # discarded by seed_kz_universities.py — restored so the researched data
    # (abbreviation, name variants, campus address) isn't thrown away.
    short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ranking: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Raw ranking string as given by a source report (e.g. "#28 (QS World)",
    # "Top-20 (Нац. рейтинг)") — kept verbatim since these mix scales
    # (global QS position, national tier, category-specific rank) that don't
    # reduce to one comparable Integer the way `ranking` implies.
    ranking_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uniranks_kz_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uniranks_world_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # "Н/Р" when checked against uniranks.com's KZ ranking and confirmed absent
    # from it; NULL means not checked yet. Kept separate from the two rank
    # columns above since those are Integer and can't hold a status string.
    uniranks_note: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # KZ-501: {"kk": "..."} — per-locale override of `description` (which holds
    # the `ru` text). Nullable, filled incrementally by KZ-504's batch
    # translation; the read side falls back to `description` (ru) when the
    # requested locale key is absent, so an empty map changes no response.
    # `ru` is never duplicated here.
    description_i18n: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    contacts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    facilities: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Per-fact provenance, same shape/rationale as Program.fact_sources —
    # {field_name: {"url": str, "checked_at": "YYYY-MM-DD"}}. See that
    # column's docstring; kept as two separate columns (not shared) since
    # University and Program facts are checked independently and at
    # different times.
    fact_sources: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    programs: Mapped[list["Program"]] = relationship("Program", back_populates="university", lazy="selectin")
    images: Mapped[list["UniversityImage"]] = relationship(
        "UniversityImage",
        back_populates="university",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="UniversityImage.is_primary.desc()",
    )

    @property
    def image_url(self) -> str | None:
        """Public URL of this university's photo, or None if there is none.

        Resolved by `slug` against the media folder's contents, NOT from the
        `images` rows — the folder is the portable source of truth, so a host
        needs only the folder (plus a DB seeded to the same slugs), never a
        copy of whatever DB the photos were first imported into. `images`
        rows are just the staging area `scripts/export_university_photos.py`
        builds that folder from.
        """
        if not self.slug:
            return None
        from app.integrations.storage.university_photos import university_photo_key
        from app.integrations.storage.urls import build_public_url

        key = university_photo_key(self.slug)
        return build_public_url(key) if key else None
