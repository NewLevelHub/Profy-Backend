"""Messages from the provider into the CRM (ТЗ §3.5, §3.12.1).

- A message from an unknown number makes a lead in «Неразобранное»: the
  number, the WhatsApp profile name, the first message, its time, the ad
  data if it came from an ad, and the source found from it.
- A message from a known number goes to the feed of the client's open deal;
  with no open deal it makes a lead marked «повторное обращение».
- Messages sent from the sales phone itself join the chat too; the CRM's own
  ones are stored when sent (`chat.send`).
- Delivery statuses update the message.

Each message is kept once (by the provider's id): a repeated webhook does
nothing. Neither phones nor texts reach the logs (ТЗ §6.2).
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.crm import (
    Attribution,
    CrmDeal,
    CrmDealEvent,
    CrmMessage,
    CrmParent,
    DealResult,
    DealStage,
    MessageDirection,
    MessageStatus,
)
from app.models.meta_ads import MetaAd
from app.services.crm import lead_source
from app.services.crm.deals import normalize_phone
from app.services.whatsapp.provider import Event, Message, StatusUpdate

logger = logging.getLogger(__name__)


def _test_numbers() -> set[str]:
    return {p for raw in settings.WHATSAPP_TEST_NUMBERS.split(",") if (p := normalize_phone(raw.strip()))}


def accepted(phone: str) -> bool:
    """With WHATSAPP_TEST_NUMBERS set (a personal number linked for a test),
    only those chats are taken in."""
    allowed = _test_numbers()
    return not allowed or phone in allowed


async def _open_deal(db: AsyncSession, parent_id: uuid.UUID) -> CrmDeal | None:
    return await db.scalar(
        select(CrmDeal)
        .where(CrmDeal.parent_id == parent_id, CrmDeal.result == DealResult.open)
        .order_by(CrmDeal.created_at.desc())
        .limit(1)
    )


async def _new_lead(db: AsyncSession, parent: CrmParent, message: Message, *, repeat: bool) -> CrmDeal:
    deal = CrmDeal(
        parent_id=parent.id, stage=DealStage.unsorted, first_message=message.text or None, repeat=repeat,
        created_at=message.at,
    )
    # «авто: реклама» — the ad's id came with the message (ТЗ §3.12.1, way 1).
    if message.ad_id and await db.get(MetaAd, message.ad_id) is not None:
        lead_source.set_automatic(deal, message.ad_id, Attribution.ad)
    db.add(deal)
    await db.flush()
    db.add(CrmDealEvent(
        deal_id=deal.id, kind="created",
        data={"stage": deal.stage.value, "via": "whatsapp", "repeat": repeat, "ad_id": message.ad_id},
    ))
    return deal


async def _message(db: AsyncSession, message: Message) -> CrmMessage | None:
    phone = normalize_phone(message.phone)
    if phone is None or not accepted(phone):
        return None
    if await db.scalar(select(CrmMessage.id).where(CrmMessage.provider_id == message.provider_id)):
        return None
    parent = await db.scalar(select(CrmParent).where(CrmParent.phone == phone).order_by(CrmParent.created_at).limit(1))
    deal = await _open_deal(db, parent.id) if parent else None

    if not message.outgoing and deal is None:
        if parent is None:
            parent = CrmParent(full_name=(message.sender_name or "").strip()[:255] or phone, phone=phone)
            db.add(parent)
            await db.flush()
            deal = await _new_lead(db, parent, message, repeat=False)
        else:
            deal = await _new_lead(db, parent, message, repeat=True)
    elif message.outgoing and deal is None and parent is not None:
        # The sales phone wrote to a client with no open deal: the last one.
        deal = await db.scalar(
            select(CrmDeal).where(CrmDeal.parent_id == parent.id).order_by(CrmDeal.created_at.desc()).limit(1)
        )

    row = CrmMessage(
        parent_id=parent.id if parent else None, deal_id=deal.id if deal else None, phone=phone,
        direction=MessageDirection.outgoing if message.outgoing else MessageDirection.incoming,
        text=message.text, kind=message.kind, provider_id=message.provider_id,
        status=MessageStatus.sent if message.outgoing else MessageStatus.received,
        ad=message.ad, at=message.at,
    )
    db.add(row)
    return row


async def handle(db: AsyncSession, events: list[Event]) -> int:
    """Apply the events; the number of messages stored. Commits."""
    stored = 0
    for event in events:
        if isinstance(event, StatusUpdate):
            row = await db.scalar(select(CrmMessage).where(CrmMessage.provider_id == event.provider_id))
            # Forward only: a late «sent» never overwrites «delivered»/«read».
            order = list(MessageStatus)
            if row is not None and order.index(event.status) > order.index(row.status):
                row.status = event.status
        elif await _message(db, event) is not None:
            stored += 1
    await db.commit()
    return stored
