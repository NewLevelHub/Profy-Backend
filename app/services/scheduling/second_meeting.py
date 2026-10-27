"""The second call, which the specialist sets themself (ТЗ §4.5, B3.5).

A tariff with «Консультация и проверка отчёта психологом» has two calls: the
first one the manager books from the CRM (`booking.book`, the system picks
the specialist), the second one — the report review — the specialist sets
for their student once the first call has begun, at any time that does not
overlap their other calls. It is 60 minutes and takes the specialist's slots
like a booking does, so the CRM no longer offers that time.

The report is published on this call; once it is marked held the deal is
«Разбор проведён» (app/services/crm/progress.py). A set call is no stage —
the CRM card shows it.
"""

import uuid
from datetime import datetime, timedelta

from fastapi import status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import CrmDeal, CrmDealEvent, DealResult
from app.models.psychologist_assignment import PsychologistStudentAssignment
from app.models.scheduling import Meeting, MeetingStatus, MeetingType, SlotState, SpecialistSlot
from app.models.user import User
from app.schemas import scheduling as schemas
from app.services import audit, tz
from app.services.crm import progress
from app.services.scheduling import grid
from app.services.scheduling.booking import ACTIVE_MEETING
from app.services.scheduling.service import scheduling_error

MINUTES = 60


def _out(meeting: Meeting | None) -> schemas.SpecialistMeeting | None:
    if meeting is None:
        return None
    return schemas.SpecialistMeeting(
        id=meeting.id, type=meeting.type, status=meeting.status, start=meeting.start_at, end=meeting.end_at,
        handoff=meeting.handoff,
    )


async def _deal(db: AsyncSession, specialist: User, student_id: uuid.UUID, *, for_update: bool = False) -> CrmDeal | None:
    """The student's open deal that this specialist serves with a review."""
    query = (
        select(CrmDeal)
        .where(
            CrmDeal.student_user_id == student_id,
            CrmDeal.specialist_id == specialist.id,
            CrmDeal.result != DealResult.lost,
            CrmDeal.psychologist_review.is_(True),
        )
        .order_by(CrmDeal.created_at.desc())
        .limit(1)
    )
    return await db.scalar(query.with_for_update() if for_update else query)


def _blocker(
    deal: CrmDeal | None, first: Meeting | None, second: Meeting | None, now: datetime
) -> schemas.SecondMeetingBlocker | None:
    if deal is None:
        return "no_consultation"
    if second is not None:
        return "already_scheduled"
    if first is None:
        return "first_not_booked"
    if first.start_at > now:
        return "first_not_started"
    return None


async def _require_student(db: AsyncSession, specialist: User, student_id: uuid.UUID) -> None:
    if not await db.scalar(
        select(PsychologistStudentAssignment.id).where(
            PsychologistStudentAssignment.psychologist_id == specialist.id,
            PsychologistStudentAssignment.student_id == student_id,
        )
    ):
        raise scheduling_error(status.HTTP_404_NOT_FOUND, "student_not_found")


async def state(db: AsyncSession, specialist: User, student_id: uuid.UUID) -> schemas.SecondMeetingState:
    await _require_student(db, specialist, student_id)
    deal = await _deal(db, specialist, student_id)
    first, second = await progress.calls(db, deal.id) if deal else (None, None)
    blocker = _blocker(deal, first, second, tz.now_utc())
    return schemas.SecondMeetingState(
        first=_out(first), second=_out(second), can_schedule=blocker is None, blocker=blocker
    )


async def _take_slots(
    db: AsyncSession, specialist_id: uuid.UUID, actor: User, meeting: Meeting, slots: list[datetime]
) -> None:
    """Mark the call's slots booked: an open slot is taken, a closed one gets
    a booked row. A slot another call holds is a conflict."""
    rows = {
        slot.start_at: slot
        for slot in (
            await db.execute(
                select(SpecialistSlot)
                .where(SpecialistSlot.specialist_id == specialist_id, SpecialistSlot.start_at.in_(slots))
                .with_for_update()
            )
        ).scalars()
    }
    if any(row.state == SlotState.booked for row in rows.values()):
        raise scheduling_error(status.HTTP_409_CONFLICT, "slot_taken")
    await db.execute(
        update(SpecialistSlot)
        .where(SpecialistSlot.specialist_id == specialist_id, SpecialistSlot.start_at.in_(list(rows)))
        .values(state=SlotState.booked, meeting_id=meeting.id, updated_by=actor.id, updated_at=func.now())
    )
    for start in slots:
        if start not in rows:
            db.add(
                SpecialistSlot(
                    specialist_id=specialist_id, start_at=start, state=SlotState.booked,
                    meeting_id=meeting.id, updated_by=actor.id,
                )
            )


async def book_own_time(
    db: AsyncSession,
    *,
    actor: User,
    specialist_id: uuid.UUID,
    start: datetime,
    minutes: int,
    deal_id: uuid.UUID | None,
    handoff: dict,
    meeting_type: MeetingType,
    rescheduled_from: uuid.UUID | None = None,
) -> Meeting:
    """A call at the specialist's own choice of time: any time on the grid
    that does not overlap their live calls — free or not in the schedule —
    and it takes those slots. The second call, and any call the specialist
    moves themself. Does not commit."""
    try:
        slots = grid.interval_slots(start, start + timedelta(minutes=minutes))
    except grid.GridError as error:
        raise scheduling_error(status.HTTP_422_UNPROCESSABLE_ENTITY, error.error_code) from None
    if slots[0] <= tz.now_utc():
        raise scheduling_error(status.HTTP_409_CONFLICT, "slot_in_past")
    end = slots[-1] + grid.SLOT
    # Any of the specialist's live calls in the way, whatever the slot rows say.
    if await db.scalar(
        select(Meeting.id).where(
            Meeting.specialist_id == specialist_id,
            Meeting.status.in_(ACTIVE_MEETING),
            Meeting.start_at < end,
            Meeting.end_at > slots[0],
        )
    ):
        raise scheduling_error(status.HTTP_409_CONFLICT, "slot_taken")
    meeting = Meeting(
        deal_id=deal_id,
        specialist_id=specialist_id,
        type=meeting_type,
        start_at=slots[0],
        end_at=end,
        handoff=dict(handoff),
        created_by=actor.id,
        rescheduled_from_id=rescheduled_from,
    )
    db.add(meeting)
    await db.flush()
    await _take_slots(db, specialist_id, actor, meeting, slots)
    return meeting


async def schedule(
    db: AsyncSession, specialist: User, student_id: uuid.UUID, start: datetime
) -> schemas.SecondMeetingState:
    await _require_student(db, specialist, student_id)
    deal = await _deal(db, specialist, student_id, for_update=True)
    first, second = await progress.calls(db, deal.id) if deal else (None, None)
    blocker = _blocker(deal, first, second, tz.now_utc())
    if blocker is not None:
        raise scheduling_error(status.HTTP_409_CONFLICT, f"second_meeting_{blocker}")
    meeting = await book_own_time(
        db, actor=specialist, specialist_id=specialist.id, start=start, minutes=MINUTES, deal_id=deal.id,
        # The specialist already knows the client; the card goes along.
        handoff=first.handoff, meeting_type=MeetingType.main60,
    )
    audit.record(
        db, actor=specialist, action="meeting.second_scheduled", entity_type="meeting", entity_id=meeting.id,
        after={"deal_id": str(deal.id), "start": meeting.start_at.isoformat()},
    )
    db.add(
        CrmDealEvent(
            deal_id=deal.id, actor_id=specialist.id, kind="booked",
            data={"start": meeting.start_at.isoformat(), "type": meeting.type.value, "second": True},
        )
    )
    await progress.sync_deal(db, deal)
    await db.commit()
    return await state(db, specialist, student_id)
