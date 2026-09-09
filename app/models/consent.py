import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# The only scope in use today: parental consent to process the psych-block
# data and to have a specialist review the validity / psychoemotional / MAC
# outputs (тестМак.md §8). Kept as a plain string (not an enum) so a new
# scope is a code-only change — see docs/psych-block-contract.md.
CONSENT_SCOPE_PSYCH_BLOCK = "psych_block"


class Consent(Base):
    """Record that a parent / legal guardian signed off. PRO-291: the fact
    is stored but does NOT block anything in the MVP — the report sections
    carry a `consent_ok: bool` annotation instead (PRO-282 §4). Multiple
    rows per user are allowed (re-sign / per-assessment); nothing here is
    unique."""

    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Free text — who signed ("Родитель: Иванова А. А." / "Законный представитель").
    signed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    scope: Mapped[str] = mapped_column(
        String(64), nullable=False, default=CONSENT_SCOPE_PSYCH_BLOCK
    )
    # NULL = blanket consent covering every assessment of this user.
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    signed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
