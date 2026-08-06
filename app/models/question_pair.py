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
    # Short scenario intro shown above the pair for ~8-10 of 34 pairs, to
    # break up visual monotony (TZ_Profi.md §14 — repetitive formats drive
    # drop-off). Null means "plain icon-pair, no story wrapper".
    frame: Mapped[str | None] = mapped_column(String, nullable=True)
