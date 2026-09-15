import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PsychologistNote(Base):
    """Psychologist's free-text note about a student (PRO-329 / Milestone 3).

    No unique constraint — a psychologist may leave many notes per student.
    Both FKs cascade with `users.id` so notes disappear with either party
    (`scripts/delete_user.py` relies on that).

    Ownership and soft-cutoff rules (create requires an active assignment;
    read/update/delete of existing notes do not) live in the service layer
    of the next ticket, not here.
    """

    __tablename__ = "psychologist_notes"

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
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
