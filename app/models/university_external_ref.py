import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UniversityExternalRef(Base):
    """Links one external source's record (e.g. jinaq institution id) to a
    University row. Populated by scripts/import_jinaq_universities.py — see
    that script's docstring for the exact-match-only linking rule (no fuzzy
    matching, mirrors scripts/apply_ovpo_codes.py). Re-running the import
    looks a record up here first, so a source id always resolves to the same
    university_id regardless of what name-matching would produce this time.
    """

    __tablename__ = "university_external_refs"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_university_external_refs_source_external_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    external_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    university_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("universities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 'exact' — matched an existing University by normalized (name, city,
    # country); 'new' — no match found, a new University row was created.
    match_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    university: Mapped["University"] = relationship("University")
