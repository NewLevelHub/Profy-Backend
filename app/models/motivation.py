import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.content_locale_column import locale_column


class MotivationCategory(str, enum.Enum):
    interest = "interest"
    challenge = "challenge"
    helping = "helping"
    freedom = "freedom"
    money = "money"
    recognition = "recognition"
    stability = "stability"
    creation = "creation"
    teamwork = "teamwork"


class MotivationStatement(Base):
    """One card in a forced-choice triplet. 3 rows share a `triplet_index`
    (one per category, never repeating within a triplet — enforced by the
    AG(2,3) generator in scripts/motivation_statement_bank.py, not here)."""

    __tablename__ = "motivation_statements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # KZ-301: natural key is (triplet_index, order); the seed dedupes on
    # (triplet_index, order, locale) in Python, no DB constraint.
    locale: Mapped[str] = locale_column()
    triplet_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category: Mapped[MotivationCategory] = mapped_column(
        Enum(MotivationCategory, name="motivation_category_enum"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(String, nullable=False)
    # Junior (6-9) rewrite of `text` — same category/position, worded around
    # school/friends/hobbies instead of career/money/work (TZ_Profi.md §13's
    # format ban doesn't apply here, this is a wording-only fix). Null means
    # "show `text` to everyone", which is what happens for middle/senior
    # always, and for junior until this is seeded.
    text_junior: Mapped[str | None] = mapped_column(String, nullable=True)


class MotivationResponse(Base):
    """One answer to one triplet: which statement was MOST important, which
    was LEAST — the third (untouched) statement is inferred at scoring time,
    never stored (app/services/motivation_service.py)."""

    __tablename__ = "motivation_responses"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id", "triplet_index", name="uq_motivation_response_assessment_triplet"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    triplet_index: Mapped[int] = mapped_column(Integer, nullable=False)
    most_statement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("motivation_statements.id", ondelete="CASCADE"), nullable=False
    )
    least_statement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("motivation_statements.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
