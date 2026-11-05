"""Changing a student's specialist: the student has one, so the change goes to
all of their deals that are still being served. Calls ahead go to the new
specialist at the same time; calls already begun stay with who had them. A
finished deal keeps its specialist in the numbers, unless it is the latest one.
"""

import logging
import uuid
from datetime import datetime

from fastapi import status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.i18n import DEFAULT_LOCALE
from app.i18n.catalog import tr
from app.models.analysis_result import AnalysisResult, ReviewStatus
from app.models.assessment import Assessment
from app.models.crm import CrmDeal, CrmStudent, DealResult
from app.models.profile import Profile
from app.models.scheduling import Meeting, SlotState, SpecialistSlot
from app.models.telegram import TelegramLink, TelegramMeetingReminder
from app.models.user import User
from app.schemas import crm as schemas
from app.services import audit, email_service, psychologist_service, tz
from app.services.crm import progress
from app.services.crm.deals import _event, _require_open, _require_owned, _users, get_deal
from app.services.crm.errors import crm_error
from app.services.crm.meetings import OPEN
from app.services.scheduling import booking, grid
from app.services.scheduling.service import active_specialists, find_specialist
from app.services.telegram import notify as telegram_notify

logger = logging.getLogger(__name__)


async def _upcoming(db: AsyncSession, deal: CrmDeal, *, for_update: bool = False) -> list[Meeting]:
    query = select(Meeting).where(
        Meeting.deal_id == deal.id, Meeting.status.in_(OPEN), Meeting.start_at > tz.now_utc()
    )
    rows = await db.execute(query.with_for_update() if for_update else query)
    return list(rows.scalars())


async def _targets(db: AsyncSession, deal: CrmDeal, *, for_update: bool = False) -> list[CrmDeal]:
    """The deal and the student's others the change applies to: open ones, ones
    with a call ahead, and the latest, which decides the student's specialist."""
    if deal.student_user_id is None:
        return [deal]
    query = (
        select(CrmDeal)
        .where(
            CrmDeal.student_user_id == deal.student_user_id,
            CrmDeal.result != DealResult.lost,
            CrmDeal.specialist_id.is_not(None),
        )
        .order_by(CrmDeal.created_at.desc())
    )
    rows = list((await db.execute(query.with_for_update() if for_update else query)).scalars())
    return [
        d
        for i, d in enumerate(rows)
        if i == 0 or d.id == deal.id or d.result == DealResult.open or await _upcoming(db, d)
    ]


def _slots(call: Meeting) -> list[datetime]:
    return grid.interval_slots(call.start_at, call.end_at)


async def options(db: AsyncSession, user: User, deal_id: uuid.UUID) -> list[schemas.SpecialistOption]:
    """Everyone the student could go to; `available` — free for all the calls
    ahead that are not theirs yet."""
    deal = await get_deal(db, user, deal_id)
    calls = [call for d in await _targets(db, deal) for call in await _upcoming(db, d)]
    wanted = {slot for call in calls for slot in _slots(call)}
    rows = await db.execute(
        select(SpecialistSlot.specialist_id, SpecialistSlot.start_at).where(
            SpecialistSlot.start_at.in_(wanted), SpecialistSlot.state == SlotState.free
        )
    )
    free = set(rows.all())
    return [
        schemas.SpecialistOption(
            id=specialist.id,
            name=specialist.full_name or specialist.email,
            available=all(
                (specialist.id, slot) in free
                for call in calls
                if call.specialist_id != specialist.id
                for slot in _slots(call)
            ),
        )
        for specialist in await active_specialists(db)
        if specialist.id != deal.specialist_id
    ]


async def change(db: AsyncSession, actor: User, deal_id: uuid.UUID, specialist_id: uuid.UUID, reason: str) -> None:
    deal = await get_deal(db, actor, deal_id, for_update=True)
    _require_owned(actor, deal)
    _require_open(deal)
    if deal.specialist_id is None:
        raise crm_error(status.HTTP_409_CONFLICT, "deal_no_specialist")
    if specialist_id == deal.specialist_id:
        raise crm_error(status.HTTP_409_CONFLICT, "specialist_same")
    new = await find_specialist(db, specialist_id)
    if new is None:
        raise crm_error(status.HTTP_404_NOT_FOUND, "specialist_not_found")

    targets = await _targets(db, deal, for_update=True)
    calls = [
        call
        for d in targets
        for call in await _upcoming(db, d, for_update=True)
        if call.specialist_id != specialist_id
    ]
    # Nothing changes unless the new specialist can take every call.
    slots = [slot for call in calls for slot in _slots(call)]
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
        raise crm_error(status.HTTP_409_CONFLICT, "specialist_not_free")

    users = await _users(
        db, {specialist_id, *(d.specialist_id for d in targets), *(call.specialist_id for call in calls)}
    )
    name = lambda user_id: (users[user_id].full_name or users[user_id].email) if user_id in users else None  # noqa: E731
    for call in calls:
        was = call.specialist_id
        await booking.release_slots(db, call, actor)
        call.specialist_id = specialist_id
        await db.execute(
            update(SpecialistSlot)
            .where(SpecialistSlot.specialist_id == specialist_id, SpecialistSlot.start_at.in_(_slots(call)))
            .values(state=SlotState.booked, meeting_id=call.id, updated_by=actor.id, updated_at=tz.now_utc())
        )
        # The new specialist gets the reminders the old one may already have had.
        await db.execute(delete(TelegramMeetingReminder).where(TelegramMeetingReminder.meeting_id == call.id))
        audit.record(
            db, actor=actor, action="meeting.specialist_changed", entity_type="meeting", entity_id=call.id,
            before={"specialist": name(was)}, after={"specialist": name(specialist_id)}, reason=reason,
        )
    for d in targets:
        was = d.specialist_id
        if was == specialist_id:
            continue
        d.specialist_id = specialist_id
        audit.record(
            db, actor=actor, action="crm.specialist_changed", entity_type="crm_deal", entity_id=d.id,
            before={"specialist": name(was)}, after={"specialist": name(specialist_id)}, reason=reason,
        )
        _event(db, d, actor, "specialist_changed", {"from": name(was), "to": name(specialist_id)}, reason)
    await progress.assign_specialist(db, deal)
    await db.commit()
    await _notify(db, new, deal)


async def _notify(db: AsyncSession, specialist: User, deal: CrmDeal) -> None:
    """Tell the new specialist, and about a report already waiting for them:
    it was announced to the old one. Best-effort: the change is committed."""
    try:
        student_id = deal.student_user_id
        crm_student = await db.get(CrmStudent, deal.student_id) if deal.student_id else None
        chat_id = await db.scalar(select(TelegramLink.chat_id).where(TelegramLink.user_id == specialist.id))
        locale = specialist.locale or DEFAULT_LOCALE
        strings = tr("telegram", locale=locale)
        student = (crm_student.full_name if crm_student else None) or strings["student_unknown"]
        path = f"/psychologist/students/{student_id}" if student_id else "/psychologist/calls"
        url = email_service.frontend_url(path)
        sends = [email_service.send_student_handover_email(specialist.email, student, locale=locale, url=url)]
        if chat_id is not None and settings.telegram_enabled:
            text = strings["student_handover"].format(student=student)
            sends.append(telegram_notify.send(None, chat_id, text, telegram_notify.button(strings["open_student"], url)))
        await psychologist_service._send_within_budget(sends)
        if student_id is None:
            return
        waiting = await db.scalar(
            select(Assessment.id)
            .join(Profile, Profile.id == Assessment.profile_id)
            .join(AnalysisResult, AnalysisResult.assessment_id == Assessment.id)
            .where(Profile.user_id == student_id, AnalysisResult.review_status == ReviewStatus.pending_review)
            .order_by(Assessment.completed_at.desc().nulls_last())
            .limit(1)
        )
        if waiting is not None:
            await psychologist_service.notify_review_pending(
                db, student_id=student_id, student_name=student, assessment_id=waiting
            )
    except Exception:
        logger.exception("crm: notifying the new specialist of deal %s failed", deal.id)
