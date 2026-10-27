"""Call reminders to the specialist's Telegram: 24 hours and 1 hour before.

The day reminder goes for a call between 1 and 24 hours away, the hour one
for a call within the hour — a call booked 40 minutes ahead gets only the
hour reminder. Each is claimed in `telegram_meeting_reminders` before it is
sent, so a repeated or concurrent check sends nothing twice; a failed send
is not retried. `run_reminders_loop` runs in the API process
(`app.main.lifespan`) only while the bot is configured, like the week
reminders (app/services/scheduling/reminders.py).
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.i18n.catalog import tr
from app.models.scheduling import Meeting, MeetingStatus
from app.models.telegram import TelegramLink, TelegramMeetingReminder
from app.models.user import User
from app.services import email_service, tz
from app.services.telegram import notify

logger = logging.getLogger(__name__)

CALLS_PATH = "/psychologist/calls"
UPCOMING = (MeetingStatus.pending, MeetingStatus.confirmed)
HOUR = timedelta(hours=1)
DAY = timedelta(hours=24)
# (kind, earliest start, latest start) relative to now.
WINDOWS = (("hour", timedelta(0), HOUR), ("day", HOUR, DAY))


def _message(meeting: Meeting, kind: str, locale: str | None) -> tuple[str, tuple[str, str] | None]:
    """The text and the «Перейти в «Созвоны»» button."""
    strings = tr("telegram", locale=locale)
    call = strings.get(f"call_{meeting.type.value}", strings["call_main60"])
    student = (meeting.handoff or {}).get("student_name") or strings["student_unknown"]
    local = tz.to_business(meeting.start_at)
    text = strings[f"reminder_{kind}"].format(
        when=strings["when"].format(date=f"{local:%d.%m}", time=f"{local:%H:%M}"), call=call, student=student
    )
    return text, notify.button(strings["open_calls"], email_service.frontend_url(CALLS_PATH))


async def send_due_reminders(db: AsyncSession, now: datetime | None = None) -> int:
    """Send every reminder that is due; returns how many went out."""
    now = now or tz.now_utc()
    sent = 0
    for kind, earliest, latest in WINDOWS:
        reminded = select(TelegramMeetingReminder.meeting_id).where(TelegramMeetingReminder.kind == kind)
        due = (
            await db.execute(
                select(Meeting, TelegramLink.chat_id, User.locale)
                .join(TelegramLink, TelegramLink.user_id == Meeting.specialist_id)
                .join(User, User.id == Meeting.specialist_id)
                .where(
                    Meeting.status.in_(UPCOMING),
                    Meeting.start_at > now + earliest,
                    Meeting.start_at <= now + latest,
                    Meeting.id.not_in(reminded),
                )
                .order_by(Meeting.start_at)
            )
        ).all()
        # Plain values: the commits below would expire the ORM objects.
        jobs = [(meeting.id, chat_id, *_message(meeting, kind, locale)) for meeting, chat_id, locale in due]
        for meeting_id, chat_id, text, button in jobs:
            claimed = (
                await db.execute(
                    insert(TelegramMeetingReminder)
                    .values(meeting_id=meeting_id, kind=kind)
                    .on_conflict_do_nothing()
                    .returning(TelegramMeetingReminder.meeting_id)
                )
            ).first()
            await db.commit()
            if claimed is None:
                continue
            if await notify.send(db, chat_id, text, button):
                sent += 1
    return sent


async def run_reminders_loop() -> None:
    """Check every `TELEGRAM_REMINDERS_INTERVAL_SECONDS` until cancelled."""
    while True:
        try:
            async with async_session() as db:
                sent = await send_due_reminders(db)
            if sent:
                logger.info("Telegram call reminders sent: %s", sent)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Telegram reminder check failed")
        await asyncio.sleep(settings.TELEGRAM_REMINDERS_INTERVAL_SECONDS)
