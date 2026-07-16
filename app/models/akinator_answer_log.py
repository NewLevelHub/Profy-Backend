import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AkinatorAnswerLog(Base):
    """Append-only history of answered turns, for calibration.

    AssessmentSession only holds the *current* belief/asked_question_ids —
    each turn overwrites the previous state, so the session row alone can't
    reconstruct which option was picked for which question at which point in
    the walk. One row here per answered question restores that chain.
    """

    __tablename__ = "akinator_answer_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("akinator_questions.id", ondelete="CASCADE"), nullable=False
    )
    # Null = "не знаю" was answered for this question.
    selected_option_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Belief snapshot immediately after this answer was scored.
    belief_after: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
