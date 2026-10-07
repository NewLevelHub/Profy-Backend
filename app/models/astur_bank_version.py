import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AsturBankVersionStatus(str, enum.Enum):
    draft = "draft"
    published = "published"


class AsturBankVersion(Base):
    """One version of the АСТУР bank (PRO-427): wording, options, keys,
    synonym tiers, scoring methods, timers and item ids travel together.

    Lifecycle `draft → validation → publish → immutable`. A draft has no
    `version` number and is freely editable; publishing validates it,
    assigns the next number and freezes `document`/`content_hash` for good —
    a change after that is a new draft, never an edit. At most one draft
    exists at a time. Every attempt (`astur_runs.bank_version_id`) points at
    the published version it was started on, forever."""

    __tablename__ = "astur_bank_versions"
    __table_args__ = (
        Index(
            "uq_astur_bank_versions_single_draft",
            "status",
            unique=True,
            postgresql_where=text("status = 'draft'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Assigned at publish; NULL while a draft.
    version: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    status: Mapped[AsturBankVersionStatus] = mapped_column(
        Enum(AsturBankVersionStatus, name="astur_bank_version_status_enum"), nullable=False
    )
    document: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # sha256 of the canonical JSON of `document`; set at publish.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # The published version this draft was branched from (key-change
    # confirmations are checked against it).
    based_on_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("astur_bank_versions.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
