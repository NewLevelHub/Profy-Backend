import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Roadmap(Base):
    __tablename__ = "roadmaps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    goal: Mapped[str] = mapped_column(String(50), nullable=False)
    focus_summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    milestones: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # 1-2 leading directions for goal in (explore, unsure); [] for profession/university.
    recommended_paths: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Hand-verified catalogue entries, see app/data/resource_catalog.py.
    additional_resources: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
