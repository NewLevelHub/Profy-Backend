"""Writing to the client from the deal's card (ТЗ §3.5), from the sales
number. Only the text goes to the provider (ТЗ §6.1)."""

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.crm import CrmDeal, CrmMessage, CrmParent, MessageDirection, MessageStatus
from app.models.user import User
from app.schemas import crm as schemas
from app.services import tz
from app.services.crm.deals import _user_ref, _users
from app.services.crm.errors import crm_error
from app.services.whatsapp import provider
from app.services.whatsapp.intake import accepted


async def send(db: AsyncSession, user: User, deal: CrmDeal, text: str) -> None:
    if not settings.whatsapp_enabled:
        raise crm_error(status.HTTP_404_NOT_FOUND, "whatsapp_disabled")
    parent = await db.get(CrmParent, deal.parent_id)
    if not parent.phone:
        raise crm_error(status.HTTP_409_CONFLICT, "whatsapp_no_phone")
    if not accepted(parent.phone):
        raise crm_error(status.HTTP_409_CONFLICT, "whatsapp_not_test_number")
    try:
        provider_id = await provider.get().send_text(parent.phone, text)
    except provider.SendError:
        raise crm_error(status.HTTP_502_BAD_GATEWAY, "whatsapp_send_failed") from None
    db.add(CrmMessage(
        parent_id=parent.id, deal_id=deal.id, phone=parent.phone, direction=MessageDirection.outgoing,
        text=text, provider_id=provider_id, status=MessageStatus.pending, author_id=user.id, at=tz.now_utc(),
    ))
    await db.commit()


async def messages(db: AsyncSession, deal: CrmDeal) -> list[schemas.MessageOut]:
    """The chat with the deal's client — all of it, not only this deal's."""
    rows = list((await db.execute(
        select(CrmMessage).where(CrmMessage.parent_id == deal.parent_id).order_by(CrmMessage.at.desc())
    )).scalars())
    authors = await _users(db, {m.author_id for m in rows})
    return [
        schemas.MessageOut(
            id=m.id, direction=m.direction.value, text=m.text, kind=m.kind, status=m.status, at=m.at,
            author=_user_ref(authors.get(m.author_id)), from_ad=bool(m.ad and m.ad.get("sourceType") == "ad"),
        )
        for m in rows
    ]
