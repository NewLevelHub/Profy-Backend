import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.i18n import DEFAULT_LOCALE, KNOWN_LOCALES


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    # KZ-405: one report row per (assessment, locale) — a `ru` and a `kk`
    # narrative for the same assessment coexist (KZ-406). Was a single-column
    # UNIQUE on assessment_id.
    __table_args__ = (
        UniqueConstraint("assessment_id", "locale", name="uq_analysis_results_assessment_id_locale"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Plain-string Enum (values, not a Python enum class) so `row.locale` is a
    # str. `locale_enum` Postgres type is owned by Alembic (d80fbf5d1f43).
    locale: Mapped[str] = mapped_column(
        Enum(*KNOWN_LOCALES, name="locale_enum", create_type=False),
        nullable=False,
        server_default=DEFAULT_LOCALE,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    profile: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # {"R": 82.0, ...}
    code: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # ["R", "I", "A"]
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # differentiation/consistency/aversion
    careers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # was `directions`
    strengths: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # ["R", "I"]
    weaknesses: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # ["C"]
    development_plan: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # {reinforce, compensate}
    big_five: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # {"N": 32.0, ...} — admin-only display
    thinking_style: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # {creative_think, systematic, strategic, practical}
    personality_highlights: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # RU phrases, merged into "Сильные стороны"
    motivation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # {"interest": 6, ...} — admin-only display
    motivation_top: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # ["interest", "creation"]
    motivation_highlights: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # RU phrases for "Что тебя драйвит"
    personality_profile: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # 5 traits, display-ready (N flipped to emotional_stability)
    personality_notes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # 1 tiered phrase per trait, for "Твой характер"
    # v2 student-report narrative fields (docs/rs-progress-notes.md) — empty
    # on every row until the narrative-generation pipeline that populates
    # them lands. [{"title": ..., "description": ...}, ...] each.
    strength_cards: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    thinking_style_notes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # 3-5 sentence synthesis tying every section together, "Итог" block.
    final_analysis: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 1 = legacy/raw-only row (every row until the v2 pipeline ships writes
    # this — it is NOT inferred from strength_cards being empty). 2 = has
    # v2 narrative, written in the same insert/commit as strength_cards/
    # thinking_style_notes so a row is never "completed" with only one of
    # the two landed.
    report_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
