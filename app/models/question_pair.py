import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.question import QuestionInstrument

LOCALIZED_FIELDS = frozenset({"frame", "option_a_text", "option_b_text"})


class QuestionPair(Base):
    """A forced-choice pair: two existing `Question` rows (same instrument),
    the user picks one. No separate response table — a submitted pick is
    written as two `UserResponse` rows (picked=5, other=1) so
    riasec_service/bigfive_service score it exactly like a Likert answer,
    unchanged (app/services/question_pair_service.py).

    Used by the ДДО «интересы» block (20 pairs, instrument
    `professional_types`), woven into the ordinary Likert flow — see
    buildDisplaySequence.ts on the frontend and
    QuestionPairItem.display_order."""

    __tablename__ = "question_pairs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Natural key is (instrument, pair_index) — one row per pair now (see
    # docs/i18n-contract.md §8), no DB constraint.
    instrument: Mapped[QuestionInstrument] = mapped_column(
        Enum(QuestionInstrument, name="question_instrument_enum", create_type=False),
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
    # (TZ_Profi.md §14 — repetitive formats drive drop-off), making the pair
    # read as one real situation. Null means "no story wrapper".
    frame: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Override for the option's displayed text — a scenario-specific action
    # ("Починить велосипед"), independent from the linked Question's own
    # Likert-statement text. Null falls back to question.short_text/text.
    # Scoring is unaffected either way — it's
    # keyed by question_a_id/question_b_id, never by displayed text.
    option_a_text: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    option_b_text: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Same idea as option_*_text but for the icon. Null falls back to
    # question.icon.
    option_a_icon: Mapped[str | None] = mapped_column(String, nullable=True)
    option_b_icon: Mapped[str | None] = mapped_column(String, nullable=True)
    # Field-name -> admin-edited value, composed on top of the bank content
    # by scripts/seed_professional_types_questions.py at resync time (see
    # docs/admin-questions-content-overrides-plan.md).
    overrides: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
