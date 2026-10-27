"""Telegram for specialists (app/services/telegram/). Contract:
docs/frontend-telegram-api-contract.md.

While the bot is not configured `GET /me` says `enabled: false` (Profile
hides the card), the other routes answer 404 `telegram_disabled`.
"""

import hmac
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import require_role
from app.models.user import User, UserRole
from app.services.telegram import links

router = APIRouter(tags=["telegram"])
_specialist = require_role(UserRole.psychologist)


class TelegramState(BaseModel):
    enabled: bool
    linked: bool
    linked_at: datetime | None = None


class TelegramLinkOut(BaseModel):
    url: str


@router.get("/me", response_model=TelegramState)
async def my_telegram(user: User = Depends(_specialist), db: AsyncSession = Depends(get_db)) -> TelegramState:
    if not settings.telegram_enabled:
        return TelegramState(enabled=False, linked=False)
    linked, since = await links.link_state(db, user)
    return TelegramState(enabled=True, linked=linked, linked_at=since)


@router.post("/me/link", response_model=TelegramLinkOut)
async def link_telegram(user: User = Depends(_specialist), db: AsyncSession = Depends(get_db)) -> TelegramLinkOut:
    return TelegramLinkOut(url=await links.create_link(db, user))


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_telegram(user: User = Depends(_specialist), db: AsyncSession = Depends(get_db)) -> None:
    links.require_enabled()
    await links.unlink(db, user)


@router.post("/webhook", include_in_schema=False)
async def webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> dict:
    """Bot updates from Telegram, signed with the secret given to setWebhook."""
    links.require_enabled()
    if secret is None or not hmac.compare_digest(secret, settings.TELEGRAM_WEBHOOK_SECRET):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    try:
        update = await request.json()
    except ValueError:
        return {}
    if isinstance(update, dict):
        await links.handle_update(db, update)
    # Always 200: anything else makes Telegram resend the same update.
    return {}
