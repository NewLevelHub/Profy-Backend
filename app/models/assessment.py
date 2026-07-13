import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AssessmentGoal(str, enum.Enum):
    explore = "explore"
    profession = "profession"
    university = "university"
    unsure = "unsure"  # "Пока не знаю" — behaves like explore


class AssessmentStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    goal: Mapped[AssessmentGoal] = mapped_column(
        Enum(AssessmentGoal, name="assessment_goal_enum"), nullable=False
    )
    status: Mapped[AssessmentStatus] = mapped_column(
        Enum(AssessmentStatus, name="assessment_status_enum"),
        nullable=False,
        default=AssessmentStatus.in_progress,
    )
    current_block: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Direction the student confirmed as a fit after the AI inquiry. Marks which
    # direction roadmap is the active one; None until a direction is confirmed.
    selected_direction_slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
