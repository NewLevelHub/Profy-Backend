import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class KnownProfessionQuiz(Base):
    """Per-leaf validation quiz for the "Уже знаю, кем хочу стать" flow.

    Same shape as ProfessionSimulation (leaf_slug unique + JSONB payload) —
    a small, purpose-built bank outside the belief-walk engine, not a row
    per question like AkinatorQuestion. `questions` is a list of:
    {"id": str, "kind": "situational"|"subject"|"commitment", "text": str,
     "options": [{"text": str, "fit_score": 0|1|2}]}
    """

    __tablename__ = "known_profession_quizzes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    leaf_slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    questions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
