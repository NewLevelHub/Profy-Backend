import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
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
    country: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ranking: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    programs: Mapped[list["Program"]] = relationship("Program", back_populates="university", lazy="selectin")
