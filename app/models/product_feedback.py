import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProductFeedback(Base):
    """Post-report feedback (TZ_Profi.md §28.4) — a short 3-question survey
    shown once after the student sees their report: a 1-5 relevance score,
    which report sections were useful (multi-pick), and an optional free-text
    note. Aggregated in the admin panel by age group / scenario / top
    direction, all derived by joining through `assessment_id` rather than
    duplicated onto every row.

    `assessment_id` is nullable (SET NULL) so a deleted assessment doesn't
    take the feedback with it; `user_id` is a hard cascade — feedback is
    personal data and goes with its owner. See scripts/delete_user.py for
    the cascade this was already anticipated for.
    """

    __tablename__ = "product_feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # "Насколько это про тебя?" — 1-5 scale. Enforced at the schema layer
    # (Pydantic Field ge/le), not a DB CHECK constraint — consistent with how
    # this codebase already handles the identical 1-5 Likert scale elsewhere
    # (no DB-level range constraint on UserResponse.answer_value either).
    relevance_score: Mapped[int] = mapped_column(Integer, nullable=False)
    # "Что оказалось самым полезным?" — multi-pick from the report's own
    # sections. Stored as free-form strings (frontend-owned list), not a DB
    # enum, so the UI can add/rename report sections without a migration.
    helpful_sections: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default='[]'
    )
    # "Что было непонятно или не подошло?" — optional free text.
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
