"""Thin Bot API client: the calls the bot makes."""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

API = "https://api.telegram.org"
TIMEOUT = httpx.Timeout(10.0)


class ChatGone(Exception):
    """The specialist blocked the bot or deleted the chat: unlink it."""


def _url(method: str) -> str:
    return f"{API}/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"


async def send_message(chat_id: int, text: str) -> bool:
    """True when Telegram took the message. Raises `ChatGone` on 403; any
    other failure is logged and reported as False — never the token."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                _url("sendMessage"),
                json={"chat_id": chat_id, "text": text, "link_preview_options": {"is_disabled": True}},
            )
    except httpx.HTTPError as error:
        logger.warning("Telegram sendMessage failed: %s", type(error).__name__)
        return False
    if response.status_code == 403:
        raise ChatGone
    if response.status_code != 200:
        logger.warning("Telegram sendMessage answered %s", response.status_code)
        return False
    return True


async def set_webhook(url: str) -> dict:
    """Point the bot's updates at `url`, signed with the webhook secret."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            _url("setWebhook"),
            json={
                "url": url,
                "secret_token": settings.TELEGRAM_WEBHOOK_SECRET,
                "allowed_updates": ["message"],
                "drop_pending_updates": True,
            },
        )
    return response.json()


async def get_updates(offset: int | None, timeout: int = 25) -> list[dict]:
    """Long-poll for updates — local runs only (scripts/telegram_poll.py),
    where Telegram cannot reach a webhook. Telegram refuses it while a
    webhook is set."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout + 10.0)) as client:
        response = await client.post(
            _url("getUpdates"), json={"offset": offset, "timeout": timeout, "allowed_updates": ["message"]}
        )
    answer = response.json()
    if not answer.get("ok"):
        raise RuntimeError(answer.get("description") or f"getUpdates answered {response.status_code}")
    return answer["result"]
