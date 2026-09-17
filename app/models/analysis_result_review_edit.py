import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AnalysisResultReviewEdit(Base):
    """Audit trail of psychologist edits to an `AnalysisResult` before it is
    published — one row per PATCH that actually changed something. Content
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
    edited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # {"field": {"old": ..., "new": ...}, ...} — only fields whose value changed.
    changed_fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
