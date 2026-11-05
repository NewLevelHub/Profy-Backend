"""A deal closed as lost takes the calls still ahead with it.

The client is gone, so the specialist must not prepare for the call and its
time goes back to the schedule. A call that has started stays as it is: it may
have been held, and its status is marked as usual. A won deal keeps its calls:
the second one can still be ahead.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.i18n.catalog import key as i18n_key
from app.i18n.catalog import tr
from app.models.crm import CrmDeal, CrmDealEvent
from app.models.scheduling import Meeting, MeetingStatus
from app.models.telegram import TelegramLink
from app.models.user import User
from app.services import audit, email_service, psychologist_service, tz
from app.services.scheduling import booking
from app.services.telegram import notify as telegram_notify

logger = logging.getLogger(__name__)

CALLS_PATH = "/psychologist/calls"


async def cancel_calls(db: AsyncSession, deal: CrmDeal, actor: User, comment: str | None) -> list[Meeting]:
    """Cancel the deal's calls ahead and free their time. Does not commit."""
    now = tz.now_utc()
    calls = list(
        await db.scalars(
            select(Meeting)
            .where(
                Meeting.deal_id == deal.id,
                Meeting.status.in_((MeetingStatus.pending, MeetingStatus.confirmed)),
                Meeting.start_at > now,
            )
            .with_for_update()
        )
    )
    closed = i18n_key("api_messages", "crm_call_cancelled_deal_closed", locale="ru")
    reason = f"{closed}: {comment}" if comment else closed
    for call in calls:
        await booking.release_slots(db, call, actor)
        call.status = MeetingStatus.cancelled
        call.cancel_reason = reason
        call.cancelled_at = now
        audit.record(
            db, actor=actor, action="meeting.cancelled", entity_type="meeting", entity_id=call.id,
            before={"status": "open", "start": call.start_at.isoformat()}, after={"status": "cancelled"},
            reason=reason,
        )
        db.add(
            CrmDealEvent(
                deal_id=deal.id, actor_id=actor.id, kind="meeting_cancelled",
                data={"start": call.start_at.isoformat()}, text=reason,
            )
        )
    return calls


async def notify_cancelled(db: AsyncSession, calls: list[Meeting]) -> None:
    """Tell each specialist about their cancelled call. Best-effort: the
    closing is committed."""
    url = email_service.frontend_url(CALLS_PATH)
    for call in calls:
        try:
            specialist = await db.get(User, call.specialist_id)
            chat_id = await db.scalar(select(TelegramLink.chat_id).where(TelegramLink.user_id == call.specialist_id))
            strings = tr("telegram", locale=specialist.locale)
            kind = strings.get(f"call_{call.type.value}", strings["call_main60"])
            student = (call.handoff or {}).get("student_name") or strings["student_unknown"]
            local = tz.to_business(call.start_at)
            when = strings["when"].format(date=f"{local:%d.%m}", time=f"{local:%H:%M}")
            sends = [email_service.send_call_cancelled_email(specialist.email, student, when, locale=specialist.locale, url=url)]
            if chat_id is not None and settings.telegram_enabled:
                text = strings["call_cancelled"].format(when=when, call=kind, student=student)
                sends.append(telegram_notify.send(None, chat_id, text, telegram_notify.button(strings["open_calls"], url)))
            await psychologist_service._send_within_budget(sends)
        except Exception:
            logger.exception("crm: notifying about the cancelled call %s failed", call.id)
