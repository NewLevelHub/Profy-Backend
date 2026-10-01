import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ExtendedBlock(str, enum.Enum):
    """The two opt-in blocks outside the main battery (Belbin/АСТУР, epic
    Тикеты-новые-тесты). Latin, matches `scripts/belbin_bank.py`/
    `scripts/astur_bank.py`'s own naming, not a coincidence — this enum's
    values are exactly the two `/assessment/extended/{block}/...` route
    segments (Ф2.6/Ф3.6)."""

    belbin = "belbin"
    astur = "astur"


class ExtendedBlockAssignment(Base):
    """A psychologist's decision to make one extended block available to a
    student for one assessment (PRO-338, post-Ф4.1 follow-up — "назначение"
    was a raw link the psychologist had to hand-deliver before this; the
    student had no way to discover the block themselves). NOT append-only
    like `belbin_runs`/`astur_runs`: one row per (assessment_id, block) —
    assigning twice is idempotent (the service returns the existing row),
    there is no "history of assignments" concept, only "is it assigned
    right now". Completion is NOT tracked here — it's derived by checking
    whether `belbin_runs`/`astur_runs` has a row for this assessment_id
    (the same append-only tables those tickets already built), so this
    table never risks drifting out of sync with the actual run data."""

    __tablename__ = "extended_block_assignments"
    __table_args__ = (
        UniqueConstraint("assessment_id", "block", name="uq_extended_block_assignment"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    block: Mapped[ExtendedBlock] = mapped_column(
        Enum(ExtendedBlock, name="extended_block_enum"), nullable=False
    )
    psychologist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
