import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SubjectReadinessStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"


class SubjectReadinessSession(Base):
    """One student's pass through the subject readiness quiz for one confirmed
    direction. Entirely separate from the Akinator engine (AssessmentSession,
    AkinatorAnswerLog, AkinatorQuestion) — references Assessment only via
    assessment_id, never writes to those tables. Submitted whole in one POST,
    so unlike AkinatorAnswerLog there is no per-step answer log."""

    __tablename__ = "subject_readiness_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    # Snapshot of Assessment.selected_direction_slug at generation time.
    direction_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    # Question ids assigned at creation, in the shuffled order shown to the
    # student (includes the noise subject's questions). Persisted so a repeat
    # GET /questions on an in_progress session returns the same set instead of
    # re-randomizing.
    question_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    # [{"question_id": str, "selected_option_index": int}, ...] — includes the
    # noise subject's answers.
    answers: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    # {"Математика": {"level": int, "interest": int, "is_strength": bool}, ...}
    # — noise subject excluded.
    subject_scores: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[SubjectReadinessStatus] = mapped_column(
        Enum(SubjectReadinessStatus, name="subject_readiness_status_enum"),
        nullable=False,
        default=SubjectReadinessStatus.in_progress,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
