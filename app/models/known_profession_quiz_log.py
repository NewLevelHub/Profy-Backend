import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class KnownProfessionQuizLog(Base):
    """Record of a completed "Уже знаю, кем хочу стать" quiz attempt.

    Mirrors ProfessionSimulationLog. assessment_id points at the sessionless
    Assessment created for this flow (see known_profession_service) — no
    AssessmentSession exists for it.
    """

    __tablename__ = "known_profession_quiz_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    leaf_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    answers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    percent: Mapped[int] = mapped_column(Integer, nullable=False)
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
