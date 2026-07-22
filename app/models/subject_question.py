import enum
import uuid
from typing import Any

from sqlalchemy import Enum, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SubjectQuestionKind(str, enum.Enum):
    level = "level"
    interest = "interest"


class SubjectQuestion(Base):
    """Question bank for the subject readiness quiz (see
    app/services/subject_readiness_service.py). Keyed by subject, not by
    specialty — a specialty only ranks subjects via Direction.subjects_required,
    so a question is never duplicated across the specialties that share a
    subject."""

    __tablename__ = "subject_questions"
    __table_args__ = (
        UniqueConstraint("subject", "kind", name="uq_subject_question_subject_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    subject: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    kind: Mapped[SubjectQuestionKind] = mapped_column(
        Enum(SubjectQuestionKind, name="subject_question_kind_enum"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # list[{"text": str, "score": 0..3}], exactly 4 options.
    options: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
