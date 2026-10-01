"""Parental / guardian consent for the psychology block (PRO-291).

The fact of consent is recorded but is NOT a gate in the MVP (PRO-282 §4):
`/result` shows the psych-block sections regardless — they carry a
`consent_ok: bool` annotation sourced from `has_consent()`. A future ticket
can promote this to a real precondition without touching call sites, since
everything routes through these two functions.
"""
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consent import CONSENT_SCOPE_PSYCH_BLOCK, Consent


async def record_consent(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    signed_by: str,
    scope: str = CONSENT_SCOPE_PSYCH_BLOCK,
    assessment_id: uuid.UUID | None = None,
) -> Consent:
    """Store one signed-consent record. `assessment_id=None` = blanket
    consent covering every assessment of this user. Flushed (not committed)
    — the caller's transaction owns the commit."""
    consent = Consent(
        user_id=user_id,
        signed_by=signed_by,
        scope=scope,
        assessment_id=assessment_id,
    )
    db.add(consent)
    await db.flush()
    return consent


async def has_consent(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    scope: str = CONSENT_SCOPE_PSYCH_BLOCK,
    assessment_id: uuid.UUID | None = None,
) -> bool:
    """True if this user has a matching consent record. A blanket record
    (`assessment_id IS NULL`) satisfies any `assessment_id` asked about; an
    assessment-scoped record only satisfies its own."""
    stmt = select(Consent.id).where(
        Consent.user_id == user_id, Consent.scope == scope
    )
    if assessment_id is not None:
        stmt = stmt.where(
            or_(Consent.assessment_id == assessment_id, Consent.assessment_id.is_(None))
        )
    result = await db.execute(stmt.limit(1))
    return result.first() is not None
