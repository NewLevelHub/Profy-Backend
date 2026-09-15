import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.assessment_validity import SdLevel, TrafficLight
from app.models.profile import AgeGroup


class ValidityCalibrationLog(Base):
    """Append-only row per completed assessment (PRO-299), incl. retakes —
    the sample used to recalibrate `validity_thresholds.json` on our own
    population once ≥300–500 protocols accumulate (psych-block-spec.md §A4).

    Distinct from `assessment_validity` (one row per assessment, overwritten
    on retake): this keeps every historical computation, plus `age_group`,
    and never has anything read it at request time.
    """

    __tablename__ = "validity_calibration_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # NOT unique — one row per completion
    )

    sd_raw: Mapped[int] = mapped_column(Integer, nullable=False)
    sd_level: Mapped[SdLevel] = mapped_column(
        Enum(SdLevel, name="sd_level_enum", create_type=False), nullable=False
    )
    longstring_max: Mapped[int] = mapped_column(Integer, nullable=False)
    irv: Mapped[float] = mapped_column(Float, nullable=False)
    infrequency_failed: Mapped[int] = mapped_column(Integer, nullable=False)
    careless_flag: Mapped[bool] = mapped_column(Boolean, nullable=False)
    traffic_light: Mapped[TrafficLight] = mapped_column(
        Enum(TrafficLight, name="traffic_light_enum", create_type=False),
        nullable=False,
    )
    age_group: Mapped[AgeGroup] = mapped_column(
        Enum(AgeGroup, name="age_group_enum", create_type=False), nullable=False
    )
    thresholds_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
