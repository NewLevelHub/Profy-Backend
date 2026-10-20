"""Writing to the change journal (`audit_log`, PRO-498)."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.user import User

SYSTEM_ACTOR = "system"


def record(
    db: AsyncSession,
    *,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
) -> AuditLog:
    """Add a journal entry to the caller's transaction (no commit here).

    `actor=None` records an automatic change made by the system."""
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_role=actor.role.value if actor else SYSTEM_ACTOR,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        before=before,
        after=after,
        reason=reason,
    )
    db.add(entry)
    return entry
