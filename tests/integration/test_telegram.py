"""Telegram for specialists (app/services/telegram/): off without the bot
settings, the deep link ties the chat, reminders 24 h and 1 h before."""

from datetime import timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.scheduling import Meeting, MeetingStatus, MeetingType
from app.models.telegram import TelegramLink
from app.models.user import User, UserRole
from app.services import tz
from app.services.telegram import client as telegram_client
from app.services.telegram import reminders
from tests.integration.test_crm_deals import _h, _user

URL = "/api/v1/telegram"
SECRET = "webhook-secret"


@pytest.fixture
def bot(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """The bot configured; messages are captured instead of sent."""
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "123:token")
    monkeypatch.setattr(settings, "TELEGRAM_BOT_USERNAME", "profile_test_bot")
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", SECRET)
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(telegram_client, "send_message", send)
    return send


def _update(chat_id: int, text: str, chat_type: str = "private") -> dict:
    return {"update_id": 1, "message": {"chat": {"id": chat_id, "type": chat_type}, "from": {"id": chat_id}, "text": text}}


async def _hook(client: httpx.AsyncClient, update: dict, secret: str = SECRET) -> httpx.Response:
    return await client.post(f"{URL}/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": secret})


async def test_off_without_the_bot_settings(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    specialist = await _user(db_session, UserRole.psychologist)
    state = await client.get(f"{URL}/me", headers=_h(specialist))
    assert state.status_code == 200 and state.json() == {"enabled": False, "linked": False, "linked_at": None}
    link = await client.post(f"{URL}/me/link", headers=_h(specialist))
    assert link.status_code == 404 and link.json()["error_code"] == "telegram_disabled"
    assert (await _hook(client, _update(1, "/start x"))).status_code == 404
    # Only specialists have it.
    student = await _user(db_session, UserRole.student)
    assert (await client.get(f"{URL}/me", headers=_h(student))).status_code == 403


async def test_the_deep_link_ties_the_chat_once(client: httpx.AsyncClient, db_session: AsyncSession, bot: AsyncMock) -> None:
    specialist = await _user(db_session, UserRole.psychologist)
    link = await client.post(f"{URL}/me/link", headers=_h(specialist))
    assert link.status_code == 200
    url = link.json()["url"]
    assert url.startswith("https://t.me/profile_test_bot?start=")
    code = url.split("start=", 1)[1]

    assert (await _hook(client, _update(555, f"/start {code}"), secret="wrong")).status_code == 403
    assert (await _hook(client, _update(555, f"/start {code}"))).status_code == 200
    assert "Telegram подключён" in bot.await_args.args[1]
    state = (await client.get(f"{URL}/me", headers=_h(specialist))).json()
    assert state["enabled"] is True and state["linked"] is True

    # The code is one-time; a group chat is ignored.
    await _hook(client, _update(777, f"/start {code}"))
    assert "Ссылка устарела" in bot.await_args.args[1]
    assert await db_session.scalar(select(TelegramLink.chat_id).where(TelegramLink.user_id == specialist.id)) == 555
    calls = bot.await_count
    await _hook(client, _update(-100, f"/start {code}", chat_type="group"))
    assert bot.await_count == calls

    # /stop in the chat, or «Отключить» in Profile, unlinks.
    await _hook(client, _update(555, "/stop"))
    assert (await client.get(f"{URL}/me", headers=_h(specialist))).json()["linked"] is False


async def _call(db: AsyncSession, specialist: User, start, status=MeetingStatus.confirmed, kind=MeetingType.intro30) -> Meeting:
    meeting = Meeting(
        specialist_id=specialist.id, type=kind, status=status, start_at=start, end_at=start + timedelta(minutes=30),
        handoff={"student_name": "Камила"},
    )
    db.add(meeting)
    await db.flush()
    return meeting


async def test_reminders_a_day_and_an_hour_before(db_session: AsyncSession, bot: AsyncMock) -> None:
    now = tz.now_utc()
    specialist = await _user(db_session, UserRole.psychologist)
    unlinked = await _user(db_session, UserRole.psychologist)
    db_session.add(TelegramLink(user_id=specialist.id, chat_id=4242))
    soon = await _call(db_session, specialist, now + timedelta(minutes=40))
    later = await _call(db_session, specialist, now + timedelta(hours=5), kind=MeetingType.main60)
    await _call(db_session, specialist, now + timedelta(hours=30))  # not yet
    await _call(db_session, specialist, now + timedelta(minutes=20), status=MeetingStatus.cancelled)
    await _call(db_session, unlinked, now + timedelta(minutes=30))  # no chat
    await db_session.flush()

    assert await reminders.send_due_reminders(db_session, now) == 2
    texts = [call.args[1] for call in bot.await_args_list]
    assert texts[0].startswith("Через час") and "первый созвон" in texts[0] and "Камила" in texts[0]
    assert texts[1].startswith("Напоминание") and "разбор отчёта" in texts[1]
    assert all(call.args[0] == 4242 for call in bot.await_args_list)
    # Nothing twice.
    assert await reminders.send_due_reminders(db_session, now) == 0

    # The day-ahead call comes within the hour: now the hour reminder.
    assert await reminders.send_due_reminders(db_session, later.start_at - timedelta(minutes=30)) == 1
    assert bot.await_args.args[1].startswith("Через час")
    assert soon.id != later.id


async def test_a_blocked_bot_unlinks_the_chat(db_session: AsyncSession, bot: AsyncMock) -> None:
    specialist = await _user(db_session, UserRole.psychologist)
    db_session.add(TelegramLink(user_id=specialist.id, chat_id=99))
    await _call(db_session, specialist, tz.now_utc() + timedelta(minutes=30))
    bot.side_effect = telegram_client.ChatGone
    assert await reminders.send_due_reminders(db_session) == 0
    assert await db_session.scalar(select(TelegramLink).where(TelegramLink.user_id == specialist.id)) is None
