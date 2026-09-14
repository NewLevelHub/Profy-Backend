import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PsychologistStudentAssignment(Base):
    """Links a psychologist to an assigned student (PRO-325 / Milestone 2).

    Both FKs point at `users.id` with CASCADE — an assignment is meaningless
    once either participant is gone, and `scripts/delete_user.py` relies on
    the user-side cascade. The (psychologist_id, student_id) uniqueness makes
    create idempotent at the DB layer.

    Participant roles (psychologist vs student) are *not* enforced here —
    validated only in the service layer on create (see
    docs/user-roles-integration-plan.md Milestone 2).
    """

    __tablename__ = "psychologist_student_assignments"
    __table_args__ = (
        UniqueConstraint(
            "psychologist_id",
            "student_id",
            name="uq_psychologist_student_assignments_pair",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    psychologist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
