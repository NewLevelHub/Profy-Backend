import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# direction_slug (String) was replaced by direction_slugs (JSONB array) in
# migration 0033. The column now holds a list of akinator specialty/section
# slugs so a single program can match multiple specialties (e.g. DevOps maps
# to both "software-engineer" and "it-infrastructure-security").

from app.database import Base


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
    direction_slugs: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    cost_per_year: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    who_its_for: Mapped[str | None] = mapped_column(Text, nullable=True)
    career_options: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    requirements: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    deadlines: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    grants: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    university: Mapped["University"] = relationship("University", back_populates="programs")
