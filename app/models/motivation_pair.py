import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.content_locale_column import locale_column
from app.models.motivation import MotivationCategory


class MotivationIntensity(str, enum.Enum):
    high = "high"  # "Точно про меня"
    medium = "medium"  # "Немного про меня"


class PairSide(str, enum.Enum):
    a = "a"
    b = "b"


class MotivationPair(Base):
    """One Harter-style forced-choice pair: 'Some kids [option_a], but other
    kids [option_b]' — junior/middle's motivation format instead of the
    3-way MOST/LEAST triplet (app/models/motivation.py), which senior keeps
    using unchanged. `category_a` always equals `category_b` — both sides
    are the SAME motivational category, option_a the positive/high pole and
    option_b the negative/low pole (genuine Harter SPPC structure, not a
    cross-category ipsative comparison — see scripts/motivation_pair_bank.py).
    Two sequential binary micro-decisions (pick a pole, then intensity) are
    cognitively lighter than holding 3 constructs at once."""

    __tablename__ = "motivation_pairs"
    # KZ-301: natural key is pair_index; one row per locale. The bare-column
    # UNIQUE this table used to carry is now (pair_index, locale).
    __table_args__ = (
        UniqueConstraint(
            "pair_index", "locale", name="uq_motivation_pairs_pair_index_locale"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    locale: Mapped[str] = locale_column()
    pair_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    category_a: Mapped[MotivationCategory] = mapped_column(
        Enum(MotivationCategory, name="motivation_category_enum", create_type=False), nullable=False
    )
    category_b: Mapped[MotivationCategory] = mapped_column(
        Enum(MotivationCategory, name="motivation_category_enum", create_type=False), nullable=False
    )
    text_a: Mapped[str] = mapped_column(String, nullable=False)
    text_b: Mapped[str] = mapped_column(String, nullable=False)


class MotivationPairResponse(Base):
    """One answer to one Harter pair: which pole (`chosen_side`) was picked
    and how strongly ('Точно про меня' vs 'Немного про меня'). `chosen_side`
    is what scoring actually keys on now — `chosen_category` alone can't
    distinguish poles since category_a == category_b on every pair. Scoring
    (app/services/motivation_pair_service.py) maps (side, intensity) to a
    1-4 Harter-style score per item: positive+high=4, positive+medium=3,
    negative+medium=2, negative+high=1."""

    __tablename__ = "motivation_pair_responses"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id", "pair_index", name="uq_motivation_pair_response_assessment_pair"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pair_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chosen_category: Mapped[MotivationCategory] = mapped_column(
        Enum(MotivationCategory, name="motivation_category_enum", create_type=False), nullable=False
    )
    chosen_side: Mapped[PairSide] = mapped_column(
        Enum(PairSide, name="motivation_pair_side_enum", create_type=False), nullable=False
    )
    intensity: Mapped[MotivationIntensity] = mapped_column(
        Enum(MotivationIntensity, name="motivation_intensity_enum"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
