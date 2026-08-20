import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.profile import AgeGroup
from app.models.question import QuestionInstrument


class QuestionPair(Base):
    """A forced-choice pair: two existing `Question` rows (same instrument),
    the user picks one. No separate response table — a submitted pick is
    written as two `UserResponse` rows (picked=5, other=1) so
    riasec_service/bigfive_service score it exactly like a Likert answer,
    unchanged (app/services/question_pair_service.py).

    Junior pairs (age_tier='junior') are the whole test, shown on their own
    screen (/assessment/pairs). Middle pairs (age_tier='middle') are woven
    into the ordinary Likert flow instead — see buildDisplaySequence.ts on
    the frontend and QuestionPairItem.display_order below. Unlike
    Question.age_tier (checked via visible_tiers(), cumulative), a pair
    belongs to exactly one age group — checked with equality, not a prefix."""

    __tablename__ = "question_pairs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    instrument: Mapped[QuestionInstrument] = mapped_column(
        Enum(QuestionInstrument, name="question_instrument_enum", create_type=False),
        nullable=False,
        index=True,
    )
    age_tier: Mapped[AgeGroup] = mapped_column(
        Enum(AgeGroup, name="age_group_enum", create_type=False),
        nullable=False,
        index=True,
    )
    pair_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    question_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    question_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    # Short scenario intro shown above the pair, to break up visual monotony
    # (TZ_Profi.md §14 — repetitive formats drive drop-off) and, for middle,
    # to make the pair read as one real situation instead of two unrelated
    # statements. Null means "plain icon-pair, no story wrapper" (junior).
    frame: Mapped[str | None] = mapped_column(String, nullable=True)
    # Override for the option's displayed text — a scenario-specific action
    # ("Починить велосипед"), independent from the linked Question's own
    # Likert-statement text. Null falls back to question.short_text/text
    # (junior's behavior, unchanged). Scoring is unaffected either way — it's
    # keyed by question_a_id/question_b_id, never by displayed text.
    option_a_text: Mapped[str | None] = mapped_column(String, nullable=True)
    option_b_text: Mapped[str | None] = mapped_column(String, nullable=True)
    # Same idea as option_*_text but for the icon — junior's format requires
    # icons (TZ_Profi.md §13), and once an option's text is rewritten as a
    # scenario-specific action, the linked Question's own icon may no longer
    # fit. Null falls back to question.icon. Middle doesn't render icons at
    # all, so its pairs leave these null.
    option_a_icon: Mapped[str | None] = mapped_column(String, nullable=True)
    option_b_icon: Mapped[str | None] = mapped_column(String, nullable=True)
