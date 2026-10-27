"""«Выставьте расписание на следующую неделю» (ТЗ §4.6 п.2, PRO-560).

From the owner's reminder moment of the current week (Friday 18:00 by
default, `scheduling_settings`) until the week ends, every active specialist
who has not published next week gets one email — and the same in Telegram
when they linked it and the bot is set up (app/services/telegram/). A
changed reminder time applies from the next check (критерий П2-08).

`run_week_reminders_loop` runs in the API process (`app.main.lifespan`)
until a job worker exists (PRO-499); `specialist_week_reminders` makes a
repeated or concurrent check send nothing twice.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.i18n.catalog import tr
from app.models.scheduling import SpecialistWeekPublication, SpecialistWeekReminder
from app.models.telegram import TelegramLink
from app.models.user import User, UserRole
from app.services import email_service, tz
from app.services.scheduling import grid, service
from app.services.telegram import notify

logger = logging.getLogger(__name__)

# Where the specialist sets their week in Profy-Frontend (PRO-551).
SCHEDULE_PATH = "/psychologist/schedule"


def _week_label(monday: date) -> str:
    sunday = monday + timedelta(days=grid.WEEK_DAYS - 1)
    return f"{monday:%d.%m}–{sunday:%d.%m.%Y}"


async def reminder_moment(db: AsyncSession, now: datetime) -> datetime:
    """This week's reminder moment, UTC."""
    current = await service.get_settings(db)
    monday = tz.week_start(tz.today(now))
    day = monday + timedelta(days=current.week_reminder_weekday - 1)
    return tz.at(day, grid.parse_wall(current.week_reminder_time))


async def send_due_week_reminders(db: AsyncSession, now: datetime | None = None) -> int:
    """Email every specialist due a reminder; returns how many were sent."""
    now = now or tz.now_utc()
    if now < await reminder_moment(db, now):
        return 0
    next_week = tz.week_start(tz.today(now)) + timedelta(days=grid.WEEK_DAYS)

    published = select(SpecialistWeekPublication.specialist_id).where(
        SpecialistWeekPublication.week_start == next_week
    )
    reminded = select(SpecialistWeekReminder.specialist_id).where(
        SpecialistWeekReminder.week_start == next_week
    )
    # Plain values, not ORM objects: the commits below would expire them.
    due = (
        await db.execute(
            select(User.id, User.email, User.full_name, User.locale, TelegramLink.chat_id)
            .outerjoin(TelegramLink, TelegramLink.user_id == User.id)
            .where(
                User.role == UserRole.psychologist,
                User.is_active.is_(True),
                User.id.not_in(published),
                User.id.not_in(reminded),
            )
        )
    ).all()

    sent = 0
    for specialist_id, email, full_name, locale, chat_id in due:
        # Claim the reminder before sending: a concurrent check that loses
        # the insert sends nothing. A failed email is not retried this week.
        claimed = (
            await db.execute(
                insert(SpecialistWeekReminder)
                .values(specialist_id=specialist_id, week_start=next_week)
                .on_conflict_do_nothing()
                .returning(SpecialistWeekReminder.specialist_id)
            )
        ).first()
        await db.commit()
        if claimed is None:
            continue
        await email_service.send_week_reminder_email(
            email,
            full_name or email,
            _week_label(next_week),
            locale=locale,
            schedule_url=email_service.frontend_url(SCHEDULE_PATH),
        )
        if chat_id is not None and settings.telegram_enabled:
            strings = tr("telegram", locale=locale)
            await notify.send(
                db,
                chat_id,
                *notify.with_link(
                    strings["week_reminder"].format(week=_week_label(next_week)),
                    email_service.frontend_url(SCHEDULE_PATH),
                    strings["open_schedule"],
                    strings["schedule_line"],
                ),
            )
        sent += 1
    return sent


async def run_week_reminders_loop() -> None:
    """Check every `WEEK_REMINDERS_INTERVAL_SECONDS` until cancelled."""
    while True:
        try:
            async with async_session() as db:
                sent = await send_due_week_reminders(db)
            if sent:
                logger.info("Week reminders sent: %s", sent)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Week reminder check failed")
        await asyncio.sleep(settings.WEEK_REMINDERS_INTERVAL_SECONDS)
