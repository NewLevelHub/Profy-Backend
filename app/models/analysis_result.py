import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.i18n import DEFAULT_LOCALE, KNOWN_LOCALES


class ReviewStatus(str, enum.Enum):
    """Psychologist review gate (docs/psychologist-review-gate-plan.md).
    A freshly generated report is `pending_review` — invisible to the
    student — until a psychologist (or an admin) publishes it."""

    pending_review = "pending_review"
    published = "published"


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
    personality_notes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # 1 tiered phrase per trait, adult wording — generation context/admin, NOT what the student reads
    # Psychologist's corrections to the student-visible "Твой характер" text
    # (trait -> text). Empty on every generated row: the student then gets the
    # age-appropriate wording computed from the scores, exactly as before the
    # review gate. Deliberately separate from `personality_notes` above, which
    # is adult-phrased for every age and feeds narrative generation.
    personality_notes_override: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
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
    # --- Psychology block (PRO-282 epic) — structurally-separate containers,
    # deliberately NOT folded into `summary`/narrative so PRO-321 (hide
    # behind role) stays a one-liner. `None` until the matching phase lands
    # its calculation (validity → Фаза 1 PRO-296…300, psychoemotional →
    # Фаза 2 PRO-307…309). Shape of each blob is owned by its phase — see
    # docs/psych-block-contract.md.
    validity: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    psychoemotional: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # PRO-338 Ф0.2 — specialist-only containers for the 4 "simple" new tests
    # (one shot per assessment, no timing/replay concerns), same JSONB-on-
    # AnalysisResult pattern as the fields above. `None` until each test's
    # own scoring service lands in Ф1 (02-Фаза1-Лёгкие-тесты.md) —
    # app/services/new_tests_report_service.py's builders treat that as "no
    # data yet", not an error. Belbin and АСТУР deliberately have NO column
    # here: their answer format (ipsative point-allocation / timed subtests)
    # needs its own table with append-only history, built in their own
    # phase (Ф2.3/Ф3.3), not a single-row JSONB snapshot.
    professional_types: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    eysenck: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    elers: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    empathy_confidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    # Specialist-only AI analysis (per-block commentary + final synthesis +
    # one profession picked from `careers`, never invented) — generated
    # lazily on first psychologist view of the report and cached here;
    # `None` until then and after an explicit regenerate. Shape owned by
    # app.schemas.psych_ai_analysis.PsychAiAnalysisOutput, not this model —
    # same "container, not a typed column" precedent as every field above.
    psych_ai_analysis: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    # Review gate. Rows that existed before the gate were backfilled to
    # `published` by the migration — they had already been shown.
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, name="analysis_result_review_status_enum"),
        nullable=False,
        default=ReviewStatus.pending_review,
        server_default=ReviewStatus.pending_review.value,
    )
    # Who last edited the content (or published without edits).
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
