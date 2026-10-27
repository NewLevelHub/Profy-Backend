"""Booked calls after the booking (ТЗ §3.9, §4.5; PRO-544, PRO-516).

The CRM calendar shows the calls, the owner works the visit window: marks the
status, moves a call or cancels it — always with a reason, into the journal.
A specialist marks their own calls in Profy. A sales manager may confirm a
call of their deal and ask the owner to move it; the request becomes the
owner's task (`tasks.request_reschedule`).
"""

import uuid
from datetime import date, datetime

from fastapi import status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.crm import CrmDeal, CrmDealEvent, CrmParent
from app.models.scheduling import Meeting, MeetingStatus, SlotState, SpecialistSlot
from app.models.user import User, UserRole
from app.schemas import crm as schemas
from app.schemas.scheduling import MAX_FREE_RANGE_DAYS as MAX_RANGE_DAYS
from app.services import audit, tz
from app.services.crm import progress
from app.services.crm.deals import SUPERVISORS, _user_ref, _users, crm_error
from app.services.scheduling import booking, second_meeting
from app.services.scheduling.service import scheduling_error

OPEN = (MeetingStatus.pending, MeetingStatus.confirmed)
# Statuses a call can get once it has started (ТЗ §4.5: not before).
AFTER_START = (MeetingStatus.done, MeetingStatus.no_show)


def _supervisor(user: User) -> bool:
    return user.role in SUPERVISORS


async def _deal_of(db: AsyncSession, meeting: Meeting) -> CrmDeal | None:
    return await db.get(CrmDeal, meeting.deal_id) if meeting.deal_id else None


async def get_meeting(db: AsyncSession, user: User, meeting_id: uuid.UUID, *, for_update: bool = False) -> Meeting:
    """The call if `user` may see it: the owner and the head of sales any, a
    sales manager the calls of their own deals, a specialist their own."""
    query = select(Meeting).where(Meeting.id == meeting_id)
    if for_update:
        query = query.with_for_update()
    meeting = await db.scalar(query)
    not_found = crm_error(status.HTTP_404_NOT_FOUND, "meeting_not_found")
    if meeting is None:
        raise not_found
    if _supervisor(user):
        return meeting
    if user.role == UserRole.psychologist:
        if meeting.specialist_id != user.id:
            raise not_found
        return meeting
    if user.role == UserRole.sales_manager:
        deal = await _deal_of(db, meeting)
        if deal is None or deal.manager_id != user.id:
            raise not_found
        return meeting
    raise not_found


def _student_name(meeting: Meeting) -> str | None:
    return (meeting.handoff or {}).get("student_name")


async def calendar(db: AsyncSession, user: User, date_from: date, date_to: date) -> list[schemas.CalendarMeeting]:
    if date_to < date_from or (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
        raise scheduling_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "range_invalid", max_days=MAX_RANGE_DAYS)
    rows = await db.execute(
        select(Meeting, CrmDeal.manager_id, CrmParent.full_name)
        .outerjoin(CrmDeal, CrmDeal.id == Meeting.deal_id)
        .outerjoin(CrmParent, CrmParent.id == CrmDeal.parent_id)
        .where(
            Meeting.start_at >= tz.day_bounds(date_from)[0],
            Meeting.start_at < tz.day_bounds(date_to)[1],
            Meeting.status != MeetingStatus.cancelled,
        )
        .order_by(Meeting.start_at)
    )
    rows = rows.all()
    names = _supervisor(user)
    users = await _users(db, {m.specialist_id for m, _, _ in rows}) if names else {}
    out = []
    for m, manager_id, parent_name in rows:
        # A sales manager sees someone else's call only as «Занято» (ТЗ §3.9 п.8):
        # no client, no deal, no specialist.
        mine = manager_id == user.id
        hidden = user.role == UserRole.sales_manager and not mine
        out.append(
            schemas.CalendarMeeting(
                id=m.id,
                deal_id=None if hidden else m.deal_id,
                type=m.type.value,
                status=m.status.value,
                start=m.start_at,
                end=m.end_at,
                student_name=None if hidden else _student_name(m),
                parent_name=None if hidden else parent_name,
                specialist=_user_ref(users.get(m.specialist_id)) if names else None,
                mine=mine,
            )
        )
    return out


async def detail(db: AsyncSession, user: User, meeting: Meeting) -> schemas.MeetingDetail:
    # The journal of this call and of the calls it was moved from.
    chain = [meeting.id]
    previous = meeting.rescheduled_from_id
    while previous and len(chain) < 20:
        chain.append(previous)
        previous = await db.scalar(select(Meeting.rescheduled_from_id).where(Meeting.id == previous))
    entries = list(
        (
            await db.execute(
                select(AuditLog)
                .where(AuditLog.entity_type == "meeting", AuditLog.entity_id.in_([str(i) for i in chain]))
                .order_by(AuditLog.at.desc())
            )
        ).scalars()
    )
    names = _supervisor(user)
    users = await _users(db, {meeting.specialist_id if names else None, *(e.actor_id for e in entries)})
    deal = await _deal_of(db, meeting)
    parent = await db.get(CrmParent, deal.parent_id) if deal else None
    allowed, first = await _may_move(db, user, meeting)
    return schemas.MeetingDetail(
        id=meeting.id,
        deal_id=meeting.deal_id,
        type=meeting.type.value,
        status=meeting.status.value,
        start=meeting.start_at,
        end=meeting.end_at,
        student_name=_student_name(meeting),
        parent_name=parent.full_name if parent else None,
        specialist=_user_ref(users.get(meeting.specialist_id)) if names else None,
        mine=deal is not None and deal.manager_id == user.id,
        handoff=meeting.handoff,
        cancel_reason=meeting.cancel_reason,
        rescheduled_from_id=meeting.rescheduled_from_id,
        call=("first" if first else "second") if deal is not None else None,
        # This user may move or cancel it now: open, not begun, their right.
        can_move=allowed and meeting.status in OPEN and tz.now_utc() < meeting.start_at,
        history=[
            schemas.MeetingHistoryItem(
                at=e.at,
                # A sales manager does not learn who the specialist is, even from the journal.
                actor=_user_ref(users.get(e.actor_id))
                if names or e.actor_role != UserRole.psychologist.value
                else None,
                actor_role=e.actor_role,
                action=e.action,
                before=e.before,
                after=e.after,
                reason=e.reason,
            )
            for e in entries
        ],
    )


def _deal_event(db: AsyncSession, meeting: Meeting, actor: User, kind: str, data: dict, text: str | None = None) -> None:
    if meeting.deal_id:
        db.add(CrmDealEvent(deal_id=meeting.deal_id, actor_id=actor.id, kind=kind, data=data, text=text))


async def _release_slots(db: AsyncSession, meeting: Meeting, actor: User) -> None:
    await db.execute(
        update(SpecialistSlot)
        .where(SpecialistSlot.meeting_id == meeting.id)
        .values(state=SlotState.free, meeting_id=None, updated_by=actor.id, updated_at=tz.now_utc())
    )


async def set_status(db: AsyncSession, actor: User, meeting: Meeting, new_status: MeetingStatus) -> Meeting:
    """`confirmed` — anyone who sees the call; `done`/`no_show` — the owner or
    the call's specialist, and only after the start (ТЗ §4.5)."""
    if meeting.status == MeetingStatus.cancelled:
        raise crm_error(status.HTTP_409_CONFLICT, "meeting_cancelled")
    if new_status in AFTER_START:
        if actor.role not in (UserRole.owner, UserRole.psychologist):
            raise crm_error(status.HTTP_403_FORBIDDEN, "meeting_action_forbidden")
        if tz.now_utc() < meeting.start_at:
            raise crm_error(status.HTTP_409_CONFLICT, "meeting_not_started")
    elif new_status == MeetingStatus.confirmed:
        if meeting.status != MeetingStatus.pending:
            raise crm_error(status.HTTP_409_CONFLICT, "meeting_status_invalid")
    else:
        raise crm_error(status.HTTP_409_CONFLICT, "meeting_status_invalid")
    if meeting.status == new_status:
        return meeting
    audit.record(
        db, actor=actor, action="meeting.status_changed", entity_type="meeting", entity_id=meeting.id,
        before={"status": meeting.status.value}, after={"status": new_status.value},
    )
    _deal_event(db, meeting, actor, "meeting_status", {"from": meeting.status.value, "to": new_status.value})
    meeting.status = new_status
    if new_status == MeetingStatus.done and (deal := await _deal_of(db, meeting)) is not None:
        # A held second call is «Разбор проведён».
        await db.flush()
        await progress.sync_deal(db, deal)
    await db.commit()
    return meeting


async def _is_first(db: AsyncSession, meeting: Meeting) -> bool:
    """The deal's first call — the one the manager booked."""
    if meeting.deal_id is None:
        return True
    first, _ = await progress.calls(db, meeting.deal_id)
    return first is None or first.id == meeting.id


async def _may_move(db: AsyncSession, actor: User, meeting: Meeting) -> tuple[bool, bool]:
    """(allowed, first). Who moves or cancels a call, always with a reason:
    the owner and the head of sales — any; a sales manager — the first call
    of their own deal; the specialist — their own calls."""
    first = await _is_first(db, meeting)
    deal = await _deal_of(db, meeting)
    allowed = (
        actor.role in SUPERVISORS
        or (actor.role == UserRole.sales_manager and first and deal is not None and deal.manager_id == actor.id)
        or (actor.role == UserRole.psychologist and meeting.specialist_id == actor.id)
    )
    return allowed, first


async def _require_movable(db: AsyncSession, actor: User, meeting: Meeting) -> bool:
    """Raises unless `actor` may move or cancel the call now (before it
    starts). Returns whether it is the deal's first call."""
    allowed, first = await _may_move(db, actor, meeting)
    if not allowed:
        raise crm_error(status.HTTP_403_FORBIDDEN, "meeting_action_forbidden")
    if meeting.status not in OPEN:
        raise crm_error(status.HTTP_409_CONFLICT, "meeting_status_invalid")
    if tz.now_utc() >= meeting.start_at:
        raise crm_error(status.HTTP_409_CONFLICT, "meeting_started")
    return first


async def cancel(db: AsyncSession, actor: User, meeting: Meeting, reason: str) -> Meeting:
    """A call cancelled before it starts; its time is free again. Without its
    first call the deal has no specialist until the next booking."""
    first = await _require_movable(db, actor, meeting)
    await _release_slots(db, meeting, actor)
    meeting.status = MeetingStatus.cancelled
    meeting.cancel_reason = reason
    meeting.cancelled_at = tz.now_utc()
    deal = await _deal_of(db, meeting)
    if first and deal is not None and deal.specialist_id == meeting.specialist_id:
        deal.specialist_id = None
    audit.record(
        db, actor=actor, action="meeting.cancelled", entity_type="meeting", entity_id=meeting.id,
        before={"status": "open", "start": meeting.start_at.isoformat()}, after={"status": "cancelled"},
        reason=reason,
    )
    _deal_event(db, meeting, actor, "meeting_cancelled", {"start": meeting.start_at.isoformat()}, reason)
    await db.commit()
    return meeting


async def reschedule(db: AsyncSession, actor: User, meeting: Meeting, start: datetime, reason: str) -> Meeting:
    """A call moved: the old one is cancelled with the reason and a new one is
    made, the handoff card goes along.

    The first call moved from the CRM is booked like a new one — with the
    same specialist when they are free then, otherwise by the usual rule
    (ТЗ §3.9 п.4). The second call, and any call the specialist moves
    themself, stays with the specialist at any time without an overlap."""
    first = await _require_movable(db, actor, meeting)
    minutes = int((meeting.end_at - meeting.start_at).total_seconds() // 60)
    was = meeting.status
    # The old call steps aside first, so the new time may overlap it; a
    # taken new time rolls the savepoint back and the call stays as it was.
    async with db.begin_nested():
        await _release_slots(db, meeting, actor)
        meeting.status = MeetingStatus.cancelled
        meeting.cancel_reason = reason
        meeting.cancelled_at = tz.now_utc()
        await db.flush()
        if first and actor.role != UserRole.psychologist:
            moved = await booking.book(
                db,
                actor=actor,
                start=start,
                minutes=minutes,
                deal_id=meeting.deal_id,
                handoff=meeting.handoff,
                prefer=meeting.specialist_id,
                rescheduled_from=meeting.id,
            )
        else:
            moved = await second_meeting.book_own_time(
                db,
                actor=actor,
                specialist_id=meeting.specialist_id,
                start=start,
                minutes=minutes,
                deal_id=meeting.deal_id,
                handoff=meeting.handoff,
                meeting_type=meeting.type,
                rescheduled_from=meeting.id,
            )
    moved.status = was
    deal = await _deal_of(db, meeting)
    if first and deal is not None:
        # The first call decides the deal's specialist.
        deal.specialist_id = moved.specialist_id
        await progress.assign_specialist(db, deal)
    audit.record(
        db, actor=actor, action="meeting.rescheduled", entity_type="meeting", entity_id=moved.id,
        before={"start": meeting.start_at.isoformat(), "meeting_id": str(meeting.id)},
        after={"start": moved.start_at.isoformat(), "same_specialist": moved.specialist_id == meeting.specialist_id},
        reason=reason,
    )
    _deal_event(
        db, meeting, actor, "meeting_moved",
        {"from": meeting.start_at.isoformat(), "to": moved.start_at.isoformat()}, reason,
    )
    await db.commit()
    return moved


async def open_meeting_for_deal(db: AsyncSession, deal_id: uuid.UUID) -> Meeting | None:
    return await db.scalar(
        select(Meeting)
        .where(Meeting.deal_id == deal_id, Meeting.status.in_(OPEN))
        .order_by(Meeting.start_at)
        .limit(1)
    )
