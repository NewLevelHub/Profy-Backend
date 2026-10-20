import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditLog(Base):
    """Append-only journal of business changes (ТЗ CRM Profile v4.1 §6.3, PRO-498).

    Who changed what, when, from what to what, and why. A database trigger
    (migration `d96ecfc9ae72`) rejects UPDATE and DELETE, so a row cannot be
    rewritten once written — through the ORM or by hand. The only update it
    lets through is `actor_id` going NULL when that account is deleted. Write through
    `app.services.audit.record` inside the transaction of the change itself,
    so the change and its journal entry commit or roll back together.

    `before`/`after` hold the changed fields only. No personal data beyond
    what the action is about, no message texts, no secrets.
    """

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_entity", "entity_type", "entity_id", "at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    # SET NULL keeps the entry when the account is deleted; `actor_role`
    # still says who it was.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Role at the time of the action, or "system" for automatic changes.
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    # Dotted verb, e.g. "schedule.availability_changed".
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
