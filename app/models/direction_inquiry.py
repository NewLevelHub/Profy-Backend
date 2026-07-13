import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DirectionInquiry(Base):
    """Persisted result of the AI direction-fit inquiry.

    Questions and answers are stored alongside the verdict so the roadmap can
    read which readiness statements the student rated low — that is the raw
    material for the growth track."""

    __tablename__ = "direction_inquiries"
    __table_args__ = (
        UniqueConstraint("assessment_id", "direction_slug", name="uq_inquiry_assessment_direction"),
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
    questions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    answers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    readiness: Mapped[str] = mapped_column(String(50), nullable=False)
    fit_summary: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
