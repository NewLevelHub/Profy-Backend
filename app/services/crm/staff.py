"""«Сотрудники» in the CRM: the owner sees the business staff — the owners,
the specialists and the CRM team. New people come by email invitation
(`/admin/invitations`, limited for the owner to
`invitation_service.OWNER_INVITABLE_ROLES`); the owner disables and enables
them here."""

import uuid

from fastapi import status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import CrmDeal, CrmParent, CrmStudent, CrmTask, DealResult
from app.models.scheduling import Meeting, MeetingStatus
from app.models.user import User, UserRole
from app.schemas import crm as schemas
from app.services import audit, tz
from app.services.crm.errors import crm_error
from app.services.invitation_service import OWNER_INVITABLE_ROLES

STAFF_ROLES = (UserRole.owner, *OWNER_INVITABLE_ROLES)
LIVE_MEETING = (MeetingStatus.pending, MeetingStatus.confirmed)


async def _upcoming(db: AsyncSession) -> dict[uuid.UUID, int]:
    """Calls still to be held: a specialist's own, a manager's on their live deals."""
    live = (Meeting.status.in_(LIVE_MEETING), Meeting.start_at > tz.now_utc())
    specialists = await db.execute(select(Meeting.specialist_id, func.count()).where(*live).group_by(Meeting.specialist_id))
    managers = await db.execute(
        select(CrmDeal.manager_id, func.count())
        .join(Meeting, Meeting.deal_id == CrmDeal.id)
        .where(*live, CrmDeal.manager_id.is_not(None), CrmDeal.result != DealResult.lost)
        .group_by(CrmDeal.manager_id)
    )
    return {**dict(specialists.all()), **dict(managers.all())}


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
    enabled again. Refused while calls are ahead: nobody would hold them, or
    follow them up. Owners are not disabled here, the owner least of all."""
    member = await db.get(User, user_id, with_for_update=True)
    if member is None or member.role not in STAFF_ROLES:
        raise crm_error(status.HTTP_404_NOT_FOUND, "staff_not_found")
    if member.role == UserRole.owner:
        raise crm_error(status.HTTP_403_FORBIDDEN, "staff_owner_locked")
    upcoming = await _upcoming(db)
    if not active and upcoming.get(member.id):
        raise crm_error(status.HTTP_409_CONFLICT, "staff_has_meetings", count=upcoming[member.id])
    if member.is_active != active:
        audit.record(
            db, actor=actor, action="crm.staff_activated" if active else "crm.staff_deactivated",
            entity_type="user", entity_id=member.id,
            before={"is_active": member.is_active}, after={"is_active": active},
        )
        member.is_active = active
        await db.commit()
    return _member(member, upcoming)


async def work(db: AsyncSession, user_id: uuid.UUID) -> schemas.StaffWork:
    """What is on an employee, for the owner before disabling or deleting them."""
    member = await db.get(User, user_id)
    if member is None or member.role not in STAFF_ROLES:
        raise crm_error(status.HTTP_404_NOT_FOUND, "staff_not_found")
    rows = await db.execute(
        select(CrmDeal, CrmParent.full_name, CrmStudent.full_name)
        .join(CrmParent, CrmParent.id == CrmDeal.parent_id)
        .outerjoin(CrmStudent, CrmStudent.id == CrmDeal.student_id)
        .where(or_(CrmDeal.manager_id == user_id, CrmDeal.specialist_id == user_id), CrmDeal.result != DealResult.lost)
        .order_by(CrmDeal.created_at.desc())
    )
    open_deals, finished = [], []
    for deal, parent_name, student_name in rows.all():
        item = schemas.StaffDeal(id=deal.id, title=" · ".join(n for n in (parent_name, student_name) if n))
        if deal.result == DealResult.open:
            open_deals.append(item)
        elif deal.specialist_id == user_id and deal.student_user_id is not None:
            finished.append(item)
    return schemas.StaffWork(
        upcoming_meetings=(await _upcoming(db)).get(user_id, 0),
        open_tasks=await db.scalar(
            select(func.count()).select_from(CrmTask).where(CrmTask.assignee_id == user_id, CrmTask.done_at.is_(None))
        ),
        open_deals=open_deals,
        finished_deals=finished,
    )
