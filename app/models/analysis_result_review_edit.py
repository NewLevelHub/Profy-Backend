import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReviewEditSource(str, enum.Enum):
    """Who made an edit. `ai_recommendation` is the system moving the AI
    analysis's recommended profession to the top of the careers list
    (psychologist_service._apply_ai_recommendation) — it has no editor
    and is not a psychologist's correction."""

    psychologist = "psychologist"
    ai_recommendation = "ai_recommendation"


class AnalysisResultReviewEdit(Base):
    """Audit trail of edits to an `AnalysisResult` before it is published —
    one row per PATCH that actually changed something, plus the system's own
    AI-recommendation reorder (`source`). Content
    is edited in place on `analysis_results`; this table is the history,
    not a draft copy (docs/psychologist-review-gate-plan.md, decision 2)."""

    __tablename__ = "analysis_result_review_edits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    analysis_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    editor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[ReviewEditSource] = mapped_column(
        Enum(ReviewEditSource, name="analysis_result_review_edit_source_enum"),
        nullable=False,
        default=ReviewEditSource.psychologist,
        server_default=ReviewEditSource.psychologist.value,
    )
    edited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # {"field": {"old": ..., "new": ...}, ...} — only fields whose value changed.
    changed_fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
