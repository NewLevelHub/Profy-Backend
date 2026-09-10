import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SdLevel(str, enum.Enum):
    """MC-SDS raw score bucketed against the versioned `sd_bounds` config
    (app/data/validity_thresholds.json)."""

    ok = "ok"  # data trustworthy
    social_desirability = "social_desirability"  # likely impression management
    high = "high"  # pronounced — data in question


class TrafficLight(str, enum.Enum):
    """Overall protocol-validity verdict shown to the specialist. Carelessness
    outranks social desirability (ТестЛжи.md §7): if the protocol is filled at
    random, impression-management is already uninformative."""

    green = "green"
    yellow = "yellow"
    red = "red"


class AssessmentValidity(Base):
    """Computed protocol-validity result for one assessment (epic PRO-282,
    phase 1). Written once by validity_service (PRO-299) after a completed
    middle/senior battery; NOT created retrospectively for older assessments.
    The `/result` `validity` section is assembled from this row
    (report_service._build_validity_section) — `null` until it exists.

    Raw per-response data (Likert answers, pair choices) stays in
    `user_response`; this table is only the aggregated verdict. Shape/meaning
    of `details` and `rt_ms` is owned by PRO-299, not a migration.
    """

    __tablename__ = "assessment_validity"
    __table_args__ = (
        CheckConstraint(
            "sd_raw >= 0 AND sd_raw <= 20",
            name="ck_assessment_validity_sd_raw_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    # --- MC-SDS ("шкала лжи") — social desirability ---
    sd_raw: Mapped[int] = mapped_column(Integer, nullable=False)  # 0–20 folded matches vs. key
    sd_level: Mapped[SdLevel] = mapped_column(
        Enum(SdLevel, name="sd_level_enum"), nullable=False
    )

    # --- Carelessness / insufficient-effort indices ---
    longstring_max: Mapped[int] = mapped_column(Integer, nullable=False)  # longest run of identical raw answers, whole battery
    irv: Mapped[float] = mapped_column(Float, nullable=False)  # inter-item SD within the protocol
    infrequency_failed: Mapped[int] = mapped_column(Integer, nullable=False)  # count of traps where answer != expected
    careless_flag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=func.false()
    )

    traffic_light: Mapped[TrafficLight] = mapped_column(
        Enum(TrafficLight, name="traffic_light_enum"), nullable=False
    )

    # Per-item breakdown: which traps failed, which items formed a run, the
    # MC-SDS item-by-item match table, D² placeholder, etc. (PRO-299).
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Passively collected inter-answer response times. NOT part of scoring
    # (ТестЛжи.md §2) — kept for future calibration only. Null if not collected.
    rt_ms: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Which `validity_thresholds.json` version produced sd_level / careless_flag.
    thresholds_version: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
