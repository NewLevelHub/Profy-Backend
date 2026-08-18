import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, Table, Text, func
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

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    university_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("universities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Direction rows this specialty prepares someone for, via the
    # program_directions FK table above — hand-mapped by
    # scripts/specialty_profession_map.py at seed time.
    directions: Mapped[list["Direction"]] = relationship(
        "Direction", secondary=program_directions, lazy="selectin", order_by="Direction.slug"
    )
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    cost_per_year: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # Free-text fallback for when cost is a range/mixed currency and doesn't
    # fit a single Decimal (e.g. "2 000 – 6 000 EUR в семестр для граждан вне
    # ЕС") — same pattern as University.ranking_label next to
    # University.ranking. UI shows cost_per_year when set, else this.
    cost_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    who_its_for: Mapped[str | None] = mapped_column(Text, nullable=True)
    career_options: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    requirements: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    deadlines: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    grants: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    university: Mapped["University"] = relationship("University", back_populates="programs")

    @property
    def profession_slugs(self) -> list[str]:
        """Read-only view of `directions` as slugs — kept so existing callers
        (schemas, roadmap_builder, direction_service) that only need the
        slug strings don't have to touch the relationship directly. Assign
        `.directions` (a list of `Direction` rows) to change the mapping,
        not this property."""
        return [d.slug for d in self.directions]
