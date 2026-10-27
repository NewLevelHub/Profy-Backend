"""«Выставьте расписание на следующую неделю» (PRO-560, критерий П2-08)."""

import uuid
from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduling import SchedulingSettings, SpecialistWeekPublication
from app.models.user import User, UserRole
from app.services import auth_service, email_service, tz
from app.services.scheduling import reminders

# A week far from real data: Monday 2030-03-04 … Sunday 2030-03-10.
MONDAY = date(2030, 3, 4)
FRIDAY = MONDAY + timedelta(days=4)
NEXT_MONDAY = MONDAY + timedelta(days=7)


@pytest.fixture
def sent(monkeypatch) -> list[dict]:
    captured: list[dict] = []

    async def _capture(to: str, name: str, week: str, *, locale: str, schedule_url: str) -> None:
        captured.append({"to": to, "name": name, "week": week, "locale": locale, "url": schedule_url})

    monkeypatch.setattr(email_service, "send_week_reminder_email", _capture)
    return captured


async def _specialist(db: AsyncSession, full_name: str | None = "Азат") -> User:
    user = User(
        email=f"{uuid.uuid4()}@example.test",
        hashed_password=auth_service.hash_password("Testpass123!"),
        is_active=True,
        is_verified=True,
        role=UserRole.psychologist,
        full_name=full_name,
        locale="kk",
    )
    db.add(user)
    await db.flush()
    return user


async def _set_reminder(db: AsyncSession, weekday: int, at: time) -> None:
    row = await db.get(SchedulingSettings, 1)
    row.week_reminder_weekday = weekday
    row.week_reminder_time = at
    await db.flush()


def _to(captured: list[dict], user: User) -> list[dict]:
    return [mail for mail in captured if mail["to"] == user.email]


async def test_reminds_once_from_friday_18(db_session: AsyncSession, sent: list[dict]) -> None:
    await _set_reminder(db_session, 5, time(18, 0))
    specialist = await _specialist(db_session)

    await reminders.send_due_week_reminders(db_session, tz.at(FRIDAY, time(17, 55)))
    assert _to(sent, specialist) == []

    await reminders.send_due_week_reminders(db_session, tz.at(FRIDAY, time(18, 5)))
    mails = _to(sent, specialist)
    assert len(mails) == 1
    assert mails[0]["name"] == "Азат"
    assert mails[0]["locale"] == "kk"
    assert mails[0]["week"] == "11.03–17.03.2030"
    assert mails[0]["url"].endswith("/psychologist/schedule")

    await reminders.send_due_week_reminders(db_session, tz.at(FRIDAY + timedelta(days=1), time(10, 0)))
    assert len(_to(sent, specialist)) == 1


async def test_published_next_week_is_not_reminded(db_session: AsyncSession, sent: list[dict]) -> None:
    await _set_reminder(db_session, 5, time(18, 0))
    specialist = await _specialist(db_session)
    db_session.add(SpecialistWeekPublication(specialist_id=specialist.id, week_start=NEXT_MONDAY))
    await db_session.flush()

    await reminders.send_due_week_reminders(db_session, tz.at(FRIDAY, time(19, 0)))
    assert _to(sent, specialist) == []


async def test_reminder_follows_changed_time(db_session: AsyncSession, sent: list[dict]) -> None:
    await _set_reminder(db_session, 4, time(10, 30))
    specialist = await _specialist(db_session, full_name=None)

    await reminders.send_due_week_reminders(db_session, tz.at(MONDAY + timedelta(days=3), time(10, 0)))
    assert _to(sent, specialist) == []
    await reminders.send_due_week_reminders(db_session, tz.at(MONDAY + timedelta(days=3), time(10, 30)))
    mails = _to(sent, specialist)
    assert len(mails) == 1
    # No name — the email address stands in.
    assert mails[0]["name"] == specialist.email


async def test_reminder_moment_is_almaty_wall_time(db_session: AsyncSession) -> None:
    await _set_reminder(db_session, 5, time(18, 0))
    moment = await reminders.reminder_moment(db_session, tz.at(MONDAY, time(9, 0)))
    # Friday 18:00 in Almaty (UTC+5) is 13:00 UTC.
    assert moment == datetime(2030, 3, 8, 13, 0, tzinfo=moment.tzinfo)


async def test_the_reminder_goes_to_telegram_too(db_session: AsyncSession, sent: list[dict], monkeypatch) -> None:
    """With the bot set up, a linked specialist gets it in Telegram as well;
    without it, only the email (app/services/telegram/)."""
    from unittest.mock import AsyncMock

    from app.config import settings
    from app.models.telegram import TelegramLink
    from app.services.telegram import client as telegram_client

    send = AsyncMock(return_value=True)
    monkeypatch.setattr(telegram_client, "send_message", send)
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://profile.example.kz")
    await _set_reminder(db_session, 5, time(18, 0))
    linked = await _specialist(db_session)
    db_session.add(TelegramLink(user_id=linked.id, chat_id=31337))
    await db_session.flush()

    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    await reminders.send_due_week_reminders(db_session, tz.at(FRIDAY, time(18, 5)))
    assert len(_to(sent, linked)) == 1 and not [c for c in send.await_args_list if c.args[0] == 31337]

    other = await _specialist(db_session)
    db_session.add(TelegramLink(user_id=other.id, chat_id=31338))
    await db_session.flush()
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "123:token")
    monkeypatch.setattr(settings, "TELEGRAM_BOT_USERNAME", "profile_test_bot")
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "secret")
    await reminders.send_due_week_reminders(db_session, tz.at(FRIDAY, time(18, 10)))
    assert len(_to(sent, other)) == 1
    (_, text, button), = [c.args for c in send.await_args_list if c.args[0] == 31338]
    # In the specialist's language (kk), with the week and the button.
    assert "11.03–17.03.2030" in text and "Дайын, апта толтырылды" in text
    assert button == ("«Кесте» бөлімін ашу", "https://profile.example.kz/psychologist/schedule")
