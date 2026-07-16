import enum
import uuid
from typing import Any

from sqlalchemy import Boolean, Enum, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class QuestionKind(str, enum.Enum):
    direct = "direct"
    situational = "situational"


class QuestionAgeVariant(str, enum.Enum):
    both = "both"
    junior = "junior"
    senior = "senior"


class AkinatorQuestion(Base):
    """New question bank for the axis-driven Akinator engine.

    Lives alongside the old `questions` table (see app/models/question.py),
    which stays untouched and keeps serving the old block-based assessment
    until [GATE] AKN-021. Axis weights inside `options` must key into
    AXIS_CODES from app/core/axes.py — enforced in the schema, not here.
    """

    __tablename__ = "akinator_questions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    kind: Mapped[QuestionKind] = mapped_column(
        Enum(QuestionKind, name="akinator_question_kind_enum"), nullable=False, index=True
    )
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    age_variant: Mapped[QuestionAgeVariant] = mapped_column(
        Enum(QuestionAgeVariant, name="akinator_question_age_variant_enum"),
        nullable=False,
        default=QuestionAgeVariant.both,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Junior-friendly rephrasing (see profi_questions_mvp.md "junior-вариант").
    # Only set when age_variant allows junior; null falls back to `text`.
    text_junior: Mapped[str | None] = mapped_column(Text, nullable=True)
    # list[{"text": str, "axis_weights": dict[str, int]}]
    options: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    # Pair of profession slugs this question is meant to disambiguate, e.g.
    # ["firefighter", "rescuer"]. Null for generic (non-resolver) questions.
    resolves_pair: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
