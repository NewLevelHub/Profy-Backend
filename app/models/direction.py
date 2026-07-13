import uuid

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Direction(Base):
    __tablename__ = "directions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Age groups this direction is offered to. Keeps adult/"heavy" directions
    # (AI, Data Science, …) out of junior/middle results, and keeps the broad
    # kid-friendly "family" directions out of senior results.
    age_groups: Mapped[list] = mapped_column(JSONB, nullable=False, default=lambda: ["senior"])
    required_scores: Mapped[dict] = mapped_column(JSONB, nullable=False)
    bonus_scores: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    professions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    skills_needed: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    subjects_to_develop: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    first_steps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
