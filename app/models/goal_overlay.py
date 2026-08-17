import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.assessment import AssessmentGoal


class GoalOverlay(Base):
    __tablename__ = "goal_overlays"
    __table_args__ = (
        UniqueConstraint("assessment_id", "goal", name="uq_goal_overlay_assessment_goal"),
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
    goal: Mapped[AssessmentGoal] = mapped_column(
        Enum(AssessmentGoal, name="assessment_goal_enum"), nullable=False
    )
    scenario: Mapped[str] = mapped_column(String(10), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
