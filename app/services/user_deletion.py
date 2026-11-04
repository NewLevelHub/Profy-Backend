"""Deleting an account for good: «Удалить» for the admin and the owner in the
panels, `scripts/delete_user.py` from the console.

The database cascades almost everything under `users`; a profile and what
hangs on it have no ON DELETE CASCADE and go here. Deals, tasks' authors and
the journal stay, with the person's id nulled by the foreign keys.
"""

import uuid

from fastapi import status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact import Artifact
from app.models.assessment import Assessment
from app.models.certificate import Certificate
from app.models.profile import Profile
from app.models.scheduling import Meeting, MeetingStatus
from app.models.user import User, UserRole
from app.services import audit, tz
from app.services.crm.errors import crm_error

# Not deleted from the panels: whoever keeps the access to them. From the console only.
LOCKED_ROLES = (UserRole.owner, UserRole.admin)
LIVE_MEETING = (MeetingStatus.pending, MeetingStatus.confirmed)


async def purge(db: AsyncSession, user: User) -> None:
    """Remove the account and its data, in foreign-key order. No commit here."""
    profile = await db.scalar(select(Profile).where(Profile.user_id == user.id))
    if profile:
        await db.execute(delete(Artifact).where(Artifact.profile_id == profile.id))
        await db.execute(delete(Certificate).where(Certificate.profile_id == profile.id))
        await db.execute(delete(Assessment).where(Assessment.profile_id == profile.id))
        await db.delete(profile)
    await db.delete(user)


async def delete_user(db: AsyncSession, actor: User, user_id: uuid.UUID) -> None:
    """A student or an employee. A specialist's upcoming calls are moved first:
    with the account they would vanish from the calendar and the clients' deals."""
    user = await db.get(User, user_id, with_for_update=True)
    if user is None:
        raise crm_error(status.HTTP_404_NOT_FOUND, "user_not_found")
    if user.id == actor.id or user.role in LOCKED_ROLES:
        raise crm_error(status.HTTP_403_FORBIDDEN, "user_delete_locked")
    upcoming = await db.scalar(
        select(func.count())
        .select_from(Meeting)
        .where(Meeting.specialist_id == user.id, Meeting.status.in_(LIVE_MEETING), Meeting.start_at > tz.now_utc())
    )
    if upcoming:
        raise crm_error(status.HTTP_409_CONFLICT, "user_has_meetings", count=upcoming)
    audit.record(
        db, actor=actor, action="user.deleted", entity_type="user", entity_id=user.id,
        before={"email": user.email, "role": user.role.value, "full_name": user.full_name},
    )
    await purge(db, user)
    await db.commit()
