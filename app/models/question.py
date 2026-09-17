import enum
import uuid

from sqlalchemy import Enum, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.profile import AgeGroup

LOCALIZED_FIELDS = frozenset({"text", "short_text"})


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
    # Protocol-validity items (epic PRO-282, phase 1; PRO-296/PRO-297). MC-SDS
    # ("шкала лжи") statements + infrequency traps, mixed into the Likert
    # battery indistinguishably from Big Five. Scored by validity_service
    # (PRO-299), NEVER picked up by riasec_service / bigfive_service — those
    # filter on `instrument` (PRO-298).
    validity = "validity"
    # PRO-338 Ф0.2: ДДО "интересы" (20 форс-чойс пар) — QuestionPair-based,
    # doesn't touch Question rows itself, but shares the same instrument
    # enum so question_service's instrument-agnostic counting/filtering
    # (assessment_shared.likert_total_questions) stays a single source of
    # truth for every instrument, pair-based or Likert-based alike.
    professional_types = "professional_types"
    # ДДО "способности" — 5 Likert-пунктов, reuses the Likert engine as-is.
    professional_types_abilities = "professional_types_abilities"
    # Eysenck EPI (темперамент), 57 Да/Нет — binary scale, see Ф0.5.
    eysenck = "eysenck"
    # Elers achievement motivation (уровень притязаний), Да/Нет — binary scale, see Ф0.5.
    elers = "elers"
    # Boyko empathy (эмпатические способности), 36 Да/Нет, 6 каналов — binary scale, see Ф0.5.
    boyko_empathy = "boyko_empathy"
    # Kondash/Prikhozhan anxiety scale, 40 items, 0-4 5-point scale
    # (Нет/Немного/Достаточно/Значительно/Очень), 4 субшкалы — see Ф1.10.
    kondash_anxiety = "kondash_anxiety"


class ValidityRole(str, enum.Enum):
    """Which kind of validity item a `instrument='validity'` question is.
    Null for every other instrument."""

    sd_key = "sd_key"  # MC-SDS social-desirability keyed item
    infrequency = "infrequency"  # attention-check "trap"


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
    # `order` is the natural key per instrument — one row per question now
    # (see docs/i18n-contract.md §8), enforced by `uq_questions_instrument_order`
    # below (migration 4d28ab54e64c). A "don't-care" order=0 is still fine in tests
    # as long as a single test never creates two same-instrument rows without
    # an explicit distinct order.
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
    # Validity module (PRO-297). Both null for non-`validity` instruments.
    #   validity_role — sd_key | infrequency (see ValidityRole).
    #   validity_meta — per-role scoring payload, kept as JSONB so the
    #     shape stays owned by the content bank / scorer, not a migration:
    #       sd_key      → {"keyed": "agree" | "disagree"}   (socially-desirable pole)
    #       infrequency → {"expected_answer": "agree" | "disagree"} (only plausible answer)
    validity_role: Mapped[ValidityRole | None] = mapped_column(
        Enum(ValidityRole, name="validity_role_enum"), nullable=True
    )
    validity_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    text: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Short button-label form of `text`, used by the junior forced-choice-pair
    # UI instead of the full Likert statement. Null for middle/senior rows.
    short_text: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
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

    __table_args__ = (
        UniqueConstraint("instrument", "order", name="uq_questions_instrument_order"),
    )
