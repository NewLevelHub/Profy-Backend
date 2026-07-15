import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SessionStatus(str, enum.Enum):
    in_progress = "in_progress"
    converged_single = "converged_single"
    converged_cluster = "converged_cluster"
    exhausted_ceiling = "exhausted_ceiling"


class AssessmentSession(Base):
    """State of the axis-driven engine's belief walk, 1:1 with an Assessment.

    The row's mere existence for an assessment_id marks that assessment as
    running on the new engine (dual-run alongside the old block flow, see
    AKN-020) — Assessment.current_block/status keep working untouched.
    """

    __tablename__ = "assessment_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    # belief per leaf direction slug, softmax-normalized (Σ ≈ 1.0). {} before
    # the first answer is scored.
    belief: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    asked_question_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    asked_axis_families: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    # Leaf slugs explicitly rejected via POST .../akinator/reject/{leaf_slug} —
    # deleted from `belief` (not just demoted), so they can never resurface.
    rejected_leaves: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resolve_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="assessment_session_status_enum"),
        nullable=False,
        default=SessionStatus.in_progress,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    # Feedback point: only set once, after a reveal (see submit_feedback).
    liked: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    feedback_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
