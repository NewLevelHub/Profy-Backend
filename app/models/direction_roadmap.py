import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DirectionRoadmap(Base):
    """AI roadmap scoped to one direction the student confirmed as a fit.

    Separate from `roadmaps` (the goal-based template roadmap): different shape
    — two layers, real curated/DB-backed facts (profession_options,
    subjects_now's weight, university_requirements) plus a thin LLM
    personalization layer (why/note text, growth_focus, starter_actions
    fallback). See app/services/roadmap_builder.py."""

    __tablename__ = "direction_roadmaps"
    __table_args__ = (
        UniqueConstraint("assessment_id", "direction_slug", name="uq_roadmap_assessment_direction"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    direction_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    direction_name: Mapped[str] = mapped_column(String(255), nullable=False)
    profession_options: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    subjects_now: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    starter_actions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    growth_focus: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    skills_to_build: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    university_requirements: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
