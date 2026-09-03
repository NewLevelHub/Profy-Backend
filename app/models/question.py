import enum
import uuid

from sqlalchemy import Enum, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.profile import AgeGroup


class HollandType(str, enum.Enum):
    R = "R"
    I = "I"
    A = "A"
    S = "S"
    E = "E"
    C = "C"


class QuestionInstrument(str, enum.Enum):
    riasec = "riasec"
    big_five = "big_five"
    mi = "mi"


class BigFiveDomain(str, enum.Enum):
    N = "N"
    E = "E"
    O = "O"
    A = "A"
    C = "C"


class Keyed(str, enum.Enum):
    plus = "plus"
    minus = "minus"


# Multiple-Intelligences-style categories replacing RIASEC for junior (6-9) —
# TZ_Profi.md §4.1 explicitly excludes career orientation for this age group,
# so junior's "interests" instrument is this instead of Holland codes.
class MIType(str, enum.Enum):
    verbal = "verbal"
    logical = "logical"
    musical = "musical"
    visual = "visual"
    bodily = "bodily"
    interpersonal = "interpersonal"
    intrapersonal = "intrapersonal"
    naturalistic = "naturalistic"


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    instrument: Mapped[QuestionInstrument] = mapped_column(
        Enum(QuestionInstrument, name="question_instrument_enum"),
        nullable=False,
        server_default="riasec",
        index=True,
    )
    riasec_type: Mapped[HollandType | None] = mapped_column(
        Enum(HollandType, name="holland_type_enum"), nullable=True, index=True
    )
    bigfive_domain: Mapped[BigFiveDomain | None] = mapped_column(
        Enum(BigFiveDomain, name="bigfive_domain_enum"), nullable=True
    )
    mi_category: Mapped[MIType | None] = mapped_column(
        Enum(MIType, name="mi_type_enum"), nullable=True
    )
    facet: Mapped[int | None] = mapped_column(Integer, nullable=True)
    keyed: Mapped[Keyed | None] = mapped_column(
        Enum(Keyed, name="keyed_enum"), nullable=True
    )
    text: Mapped[str] = mapped_column(String, nullable=False)
    # Short button-label form of `text`, used by the junior forced-choice-pair
    # UI instead of the full Likert statement. Null for middle/senior rows.
    short_text: Mapped[str | None] = mapped_column(String, nullable=True)
    # Single emoji rendered as the "icon" the junior format requires
    # (TZ_Profi.md §13 — junior's allowed formats all mandate icons).
    icon: Mapped[str | None] = mapped_column(String, nullable=True)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Minimum age branch this question is shown to — junior sees only
    # age_tier='junior' rows, middle sees junior+middle, senior sees all
    # (app/services/age_tiers.py:visible_tiers). Reuses profiles' own
    # age_group_enum Postgres type, not a duplicate.
    age_tier: Mapped[AgeGroup] = mapped_column(
        Enum(AgeGroup, name="age_group_enum", create_type=False),
        nullable=False,
        server_default="senior",
        index=True,
    )
    # Field-name -> admin-edited value, composed on top of the bank content
    # by every scripts/seed_*.py at resync time so admin edits survive
    # redeploys (see docs/admin-questions-content-overrides-plan.md).
    overrides: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
