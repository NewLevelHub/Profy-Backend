"""The lead's source — one field (ТЗ §3.12.1): a Meta ad, or a source of the
list that is not an ad («рекомендация», «повторный клиент», «органика
Instagram», …). Found, by priority: the ad's id in the WhatsApp message
(«авто: реклама»), the ad's greeting in its text («авто: приветствие»), the
manager's pick («вручную»); none — «Креатив не определён».

The manager does not change an automatic one; the head of sales or the owner
corrects it, and the correction is a manual one. Every change is journaled.
"""

import uuid

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import Attribution, CrmDeal, CrmSource
from app.models.meta_ads import MetaAd
from app.models.user import User, UserRole
from app.schemas import crm as schemas
from app.services import audit
from app.services.crm import sources
from app.services.crm.errors import crm_error

AUTOMATIC = (Attribution.ad, Attribution.greeting)
_SUPERVISORS = (UserRole.owner, UserRole.sales_head)


async def describe(db: AsyncSession, deals: list[CrmDeal]) -> dict[uuid.UUID, schemas.LeadSource]:
    """Each deal's source, for the board and the card; deals without one are absent."""
    ad_ids = {d.meta_ad_id for d in deals if d.meta_ad_id}
    source_ids = {d.source_id for d in deals if d.source_id}
    ads = {a.id: a for a in (await db.execute(select(MetaAd).where(MetaAd.id.in_(ad_ids)))).scalars()} if ad_ids else {}
    names = dict((await db.execute(
        select(CrmSource.id, CrmSource.name).where(CrmSource.id.in_(source_ids))
    )).all()) if source_ids else {}
    out = {}
    for deal in deals:
        if deal.meta_ad_id and (ad := ads.get(deal.meta_ad_id)):
            out[deal.id] = schemas.LeadSource(
                kind="ad", id=ad.id, name=ad.name, campaign_name=ad.campaign_name, adset_name=ad.adset_name,
                attribution=deal.attribution,
            )
        elif deal.source_id and deal.source_id in names:
            out[deal.id] = schemas.LeadSource(
                kind="source", id=str(deal.source_id), name=names[deal.source_id], attribution=deal.attribution
            )
    return out


def _snapshot(deal: CrmDeal) -> dict:
    return {
        "meta_ad_id": deal.meta_ad_id,
        "source_id": str(deal.source_id) if deal.source_id else None,
        "attribution": deal.attribution.value if deal.attribution else None,
    }


async def pick(db: AsyncSession, user: User, deal: CrmDeal, choice: schemas.SourcePick | None) -> bool:
    """The manager's pick («вручную»), or `None` to clear it. True when it
    changed; the caller commits. The feed event is the caller's too."""
    ad_id = choice.ad_id if choice else None
    source_id = choice.source_id if choice else None
    if (ad_id, source_id) == (deal.meta_ad_id, deal.source_id):
        return False
    if deal.attribution in AUTOMATIC and user.role not in _SUPERVISORS:
        raise crm_error(status.HTTP_403_FORBIDDEN, "attribution_auto_locked")
    if ad_id is not None and await db.get(MetaAd, ad_id) is None:
        raise crm_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "ad_not_found")
    source_id = await sources.pickable(db, source_id, deal.source_id)
    before = _snapshot(deal)
    deal.meta_ad_id, deal.source_id = ad_id, source_id
    deal.attribution = Attribution.manual if choice else None
    if deal.id is not None and before != (after := _snapshot(deal)):
        audit.record(
            db, actor=user, action="crm.source_changed", entity_type="crm_deal", entity_id=deal.id,
            before=before, after=after,
        )
    return True


def set_automatic(deal: CrmDeal, ad_id: str, attribution: Attribution) -> None:
    """For the WhatsApp intake: the ad found from the message. A manual pick
    stays — the automatic one only fills an empty source."""
    if deal.meta_ad_id is None and deal.source_id is None:
        deal.meta_ad_id, deal.attribution = ad_id, attribution

