import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FeedbackRating(str, enum.Enum):
    good = "good"
    neutral = "neutral"
    bad = "bad"


class ProductFeedback(Base):
    """Product-level feedback (e.g. roadmap rating) — distinct from the
    per-leaf like/dislike collected during the Akinator reveal, which lives
    on AssessmentSession and is really a direction-selection signal, not a
    product opinion.
    """

    __tablename__ = "product_feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="SET NULL"), nullable=True
    )
    # Stored explicitly rather than derived from assessments.selected_direction_slug,
    # so the record stays accurate even if the user later confirms a different direction.
    direction_slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Where the feedback was collected (e.g. "roadmap"). Plain string, not a
    # Postgres enum — more contexts land in later iterations, and adding
    # native enum values needs its own migration each time.
    context: Mapped[str] = mapped_column(String(30), nullable=False)
    rating: Mapped[FeedbackRating] = mapped_column(
        Enum(FeedbackRating, name="product_feedback_rating_enum"), nullable=False
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
