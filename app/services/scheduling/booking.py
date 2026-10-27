"""Booking a call into the shared schedule (ТЗ §3.9, PRO-544).

The manager picks a time without seeing who is free; the system picks the
specialist — fewest meetings this week, then fewest today, then at random
(п.4) — and takes the slots atomically (п.5): the slot rows are locked with
`SELECT … FOR UPDATE`, and under READ COMMITTED Postgres re-checks the
`state = 'free'` condition on the locked rows, so of two managers racing for
the last slot exactly one gets it and the other gets `slot_taken`.
"""

import random
import uuid
from datetime import datetime, timedelta

from fastapi import status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduling import Meeting, MeetingStatus, MeetingType, SlotState, SpecialistSlot
from app.models.user import User, UserRole
from app.services import tz
from app.services.scheduling import grid
from app.services.scheduling.service import scheduling_error

ACTIVE_MEETING = (MeetingStatus.pending, MeetingStatus.confirmed, MeetingStatus.done)


def meeting_type(minutes: int) -> MeetingType:
    return MeetingType.intro30 if minutes == 30 else MeetingType.main60


async def _meeting_counts(
    db: AsyncSession, specialist_ids: list[uuid.UUID], start: datetime, end: datetime
) -> dict[uuid.UUID, int]:
    rows = await db.execute(
        select(Meeting.specialist_id, func.count())
        .where(
            Meeting.specialist_id.in_(specialist_ids),
            Meeting.status.in_(ACTIVE_MEETING),
            Meeting.start_at >= start,
            Meeting.start_at < end,
        )
        .group_by(Meeting.specialist_id)
    )
    return dict(rows.all())


async def _candidates(db: AsyncSession, slots: list[datetime], start: datetime) -> list[uuid.UUID]:
    """Specialists free for every slot, in the order ТЗ §3.9 п.4 prefers them."""
    rows = await db.execute(
        select(SpecialistSlot.specialist_id)
        .join(User, User.id == SpecialistSlot.specialist_id)
        .where(
            SpecialistSlot.start_at.in_(slots),
            SpecialistSlot.state == SlotState.free,
            User.role == UserRole.psychologist,
            User.is_active.is_(True),
        )
        .group_by(SpecialistSlot.specialist_id)
        .having(func.count() == len(slots))
    )
    ids = [row[0] for row in rows.all()]
    if not ids:
        return []
    day = tz.business_date(start)
    monday = tz.week_start(day)
    week = await _meeting_counts(db, ids, tz.day_bounds(monday)[0], tz.day_bounds(monday + timedelta(days=6))[1])
    today = await _meeting_counts(db, ids, *tz.day_bounds(day))
    tie = {specialist_id: random.random() for specialist_id in ids}
    return sorted(ids, key=lambda i: (week.get(i, 0), today.get(i, 0), tie[i]))


async def book(
    db: AsyncSession,
    *,
    actor: User,
    start: datetime,
    minutes: int,
    deal_id: uuid.UUID | None,
    handoff: dict,
    now: datetime | None = None,
) -> Meeting:
    """Create the meeting and take its slots. Does not commit."""
    now = now or tz.now_utc()
    try:
        slots = grid.interval_slots(start, start + timedelta(minutes=minutes))
    except grid.GridError as error:
        raise scheduling_error(status.HTTP_422_UNPROCESSABLE_ENTITY, error.error_code) from None
    if slots[0] <= now:
        raise scheduling_error(status.HTTP_409_CONFLICT, "slot_in_past")

    for specialist_id in await _candidates(db, slots, start):
        locked = await db.execute(
            select(SpecialistSlot.start_at)
            .where(
                SpecialistSlot.specialist_id == specialist_id,
                SpecialistSlot.start_at.in_(slots),
                SpecialistSlot.state == SlotState.free,
            )
            .with_for_update()
        )
        if len(locked.all()) != len(slots):
            continue  # taken meanwhile by another booking; try the next one
        meeting = Meeting(
            deal_id=deal_id,
            specialist_id=specialist_id,
            type=meeting_type(minutes),
            start_at=slots[0],
            end_at=slots[-1] + grid.SLOT,
            handoff=handoff,
            created_by=actor.id,
        )
        db.add(meeting)
        await db.flush()
        await db.execute(
            update(SpecialistSlot)
            .where(SpecialistSlot.specialist_id == specialist_id, SpecialistSlot.start_at.in_(slots))
            .values(state=SlotState.booked, meeting_id=meeting.id, updated_by=actor.id, updated_at=func.now())
        )
        return meeting

    raise scheduling_error(status.HTTP_409_CONFLICT, "slot_taken")
