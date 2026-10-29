"""«Сотрудники» in the CRM: the owner sees the business staff — the owners,
the specialists and the CRM team. New people come by email invitation
(`/admin/invitations`, limited for the owner to
`invitation_service.OWNER_INVITABLE_ROLES`); the owner disables and enables
them here."""

import uuid

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduling import Meeting, MeetingStatus
from app.models.user import User, UserRole
from app.schemas import crm as schemas
from app.services import audit, tz
from app.services.crm.errors import crm_error
from app.services.invitation_service import OWNER_INVITABLE_ROLES

STAFF_ROLES = (UserRole.owner, *OWNER_INVITABLE_ROLES)
LIVE_MEETING = (MeetingStatus.pending, MeetingStatus.confirmed)


async def _upcoming(db: AsyncSession) -> dict[uuid.UUID, int]:
    rows = await db.execute(
        select(Meeting.specialist_id, func.count())
        .where(Meeting.status.in_(LIVE_MEETING), Meeting.start_at > tz.now_utc())
        .group_by(Meeting.specialist_id)
    )
    return dict(rows.all())


def _member(user: User, upcoming: dict[uuid.UUID, int]) -> schemas.StaffMember:
    return schemas.StaffMember(
        id=user.id, email=user.email, full_name=user.full_name, role=user.role.value, is_active=user.is_active,
        created_at=user.created_at, upcoming_meetings=upcoming.get(user.id, 0),
    )


async def members(db: AsyncSession) -> list[schemas.StaffMember]:
    rows = await db.execute(
        select(User).where(User.role.in_(STAFF_ROLES)).order_by(User.is_active.desc(), User.full_name, User.email)
    )
    upcoming = await _upcoming(db)
    return [_member(u, upcoming) for u in rows.scalars()]


async def set_active(db: AsyncSession, actor: User, user_id: uuid.UUID, active: bool) -> schemas.StaffMember:
    """A disabled account cannot sign in or call the API (`get_current_user`
    checks `is_active`), and a disabled specialist drops out of the free-time
    summary and the booking at once — their slots stay, for when they are
    enabled again. Owners are not disabled here, the owner least of all."""
    member = await db.get(User, user_id, with_for_update=True)
    if member is None or member.role not in STAFF_ROLES:
        raise crm_error(status.HTTP_404_NOT_FOUND, "staff_not_found")
    if member.role == UserRole.owner:
        raise crm_error(status.HTTP_403_FORBIDDEN, "staff_owner_locked")
    if member.is_active != active:
        audit.record(
            db, actor=actor, action="crm.staff_activated" if active else "crm.staff_deactivated",
            entity_type="user", entity_id=member.id,
            before={"is_active": member.is_active}, after={"is_active": active},
        )
        member.is_active = active
        await db.commit()
    return _member(member, await _upcoming(db))
