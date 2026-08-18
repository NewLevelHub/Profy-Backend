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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    programs: Mapped[list["Program"]] = relationship("Program", back_populates="university", lazy="selectin")
