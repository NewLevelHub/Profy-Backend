"""«Подключить Telegram»: the specialist opens a one-time deep link
t.me/<bot>?start=<code>; Telegram sends the bot `/start <code>` from their
chat, and the chat is tied to the account."""

import secrets
import uuid
from datetime import datetime, timedelta

from fastapi import status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import AppError
from app.i18n.catalog import key as i18n_key
from app.i18n.catalog import tr
from app.models.telegram import TelegramLink, TelegramLinkCode
from app.models.user import User
from app.services import tz
from app.services.telegram import client
from app.services.token_utils import hash_code

LINK_TTL = timedelta(minutes=30)


def require_enabled() -> None:
    if not settings.telegram_enabled:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="telegram_disabled",
            detail=i18n_key("api_errors", "telegram_disabled"),
        )


async def link_state(db: AsyncSession, user: User) -> tuple[bool, datetime | None]:
    """(linked, since)."""
    linked_at = await db.scalar(select(TelegramLink.linked_at).where(TelegramLink.user_id == user.id))
    return linked_at is not None, linked_at


async def create_link(db: AsyncSession, user: User) -> str:
    """A fresh deep link; the previous one stops working."""
    require_enabled()
    code = secrets.token_urlsafe(24)  # 32 chars of [A-Za-z0-9_-]: what /start accepts
    await db.execute(delete(TelegramLinkCode).where(TelegramLinkCode.user_id == user.id))
    db.add(TelegramLinkCode(user_id=user.id, code_hash=hash_code(code), expires_at=tz.now_utc() + LINK_TTL))
    await db.commit()
    return f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={code}"


async def unlink(db: AsyncSession, user: User) -> None:
    await db.execute(delete(TelegramLink).where(TelegramLink.user_id == user.id))
    await db.execute(delete(TelegramLinkCode).where(TelegramLinkCode.user_id == user.id))
    await db.commit()


def _locale(sender: dict) -> str:
    return "kk" if sender.get("language_code") == "kk" else "ru"


async def handle_update(db: AsyncSession, update: dict) -> None:
    """One webhook update. Only private `/start` and `/stop` mean anything."""
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    text = (message.get("text") or "").strip()
    chat_id = chat.get("id")
    if chat.get("type") != "private" or not isinstance(chat_id, int) or not text.startswith("/"):
        return
    command, _, argument = text.partition(" ")
    command = command.split("@", 1)[0]
    strings = tr("telegram", locale=_locale(message.get("from") or {}))

    if command == "/stop":
        await db.execute(delete(TelegramLink).where(TelegramLink.chat_id == chat_id))
        await db.commit()
        await _reply(chat_id, strings["stopped"])
        return
    if command != "/start":
        return
    if not argument.strip():
        await _reply(chat_id, strings["start_without_code"])
        return

    row = await db.scalar(
        select(TelegramLinkCode).where(TelegramLinkCode.code_hash == hash_code(argument.strip())).with_for_update()
    )
    if row is None or row.expires_at <= tz.now_utc():
        await _reply(chat_id, strings["link_invalid"])
        return
    user_id: uuid.UUID = row.user_id
    # One chat per account and one account per chat: the latest link wins.
    await db.execute(delete(TelegramLink).where((TelegramLink.user_id == user_id) | (TelegramLink.chat_id == chat_id)))
    await db.delete(row)
    db.add(TelegramLink(user_id=user_id, chat_id=chat_id))
    user = await db.get(User, user_id)
    await db.commit()
    await _reply(chat_id, tr("telegram", locale=user.locale if user else None)["linked"])


async def _reply(chat_id: int, text: str) -> None:
    try:
        await client.send_message(chat_id, text)
    except client.ChatGone:
        pass
