import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AsturRunStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"
    # Superseded or unusable protocol; kept for history, never interpreted.
    invalidated = "invalidated"


class AsturRun(Base):
    """One АСТУР attempt (PRO-338 Ф3.3, lifecycle PRO-427).

    Append-only history per assessment. An attempt is filled in per subtest
    (`answers[subtest_key]`, `lability_answers` for quick instructions) and
    finalized atomically by the submit that delivers its last required
    block: status flips to `completed`, and the scored result is frozen into
    `result_snapshot` together with `scoring_version`. A completed attempt is
    never rescored, never extended; a new attempt exists only after an
    explicit retake. At most one attempt per assessment is `in_progress`.

    `bank_version_id` pins the bank version the respondent actually saw —
    scoring reads keys from that version, never from the latest one."""

    __tablename__ = "astur_runs"
    __table_args__ = (
        Index(
            "uq_astur_runs_single_active",
            "assessment_id",
            unique=True,
            postgresql_where=text("status = 'in_progress'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    locale: Mapped[str] = mapped_column(String, nullable=False, default="ru")
    status: Mapped[AsturRunStatus] = mapped_column(
        Enum(AsturRunStatus, name="astur_run_status_enum"),
        nullable=False,
        default=AsturRunStatus.in_progress,
        server_default=AsturRunStatus.in_progress.value,
    )
    bank_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("astur_bank_versions.id", ondelete="RESTRICT"), nullable=False
    )

    # --- Raw protocol (never deleted, never rewritten after completion) ---
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    subtest_timings_ms: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # {subtest_key: ISO timestamp} — server clock anchor of each subtest timer.
    subtest_started_at: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # {"1".."N": {"answer", "elapsed_ms", "over_limit", "answered_at"}}
    lability_answers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # IANA timezone reported with the quick-instructions block.
    client_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # --- Frozen at finalize ---
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scoring_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Hash of the bank version document the attempt was scored against.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # app.schemas.astur.AsturResultSnapshot
    result_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Same value as result_snapshot["protocol_quality"], kept queryable.
    protocol_quality: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
