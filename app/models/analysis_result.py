import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    profile: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # {"R": 82.0, ...}
    code: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # ["R", "I", "A"]
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # differentiation/consistency/aversion
    careers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # was `directions`
    strengths: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # ["R", "I"]
    weaknesses: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # ["C"]
    development_plan: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # {reinforce, compensate}
    big_five: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # {"N": 32.0, ...} — admin-only display
    thinking_style: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # {creative_think, systematic, strategic, practical}
    personality_highlights: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # RU phrases, merged into "Сильные стороны"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
