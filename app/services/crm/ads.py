"""Ads in the CRM (ТЗ §3.12): Meta's numbers per ad next to the deals that
came from it, so the CRM counts the cost of a lead, of a target lead and of
a client (CAC) itself (doc «Meta Marketing API — подключение», §2).

The period is a cohort, as on the «Аналитика» page: spend of the days in it
and deals created in it. Spend is in the account's USD; ₸ by the rate the
owner entered for the day (`meta_fx_rates`, the latest from before the day).
A deal is tied to an ad by hand («Креатив» on the deal) until WhatsApp
brings each ad's greeting tag; a deal without one is «Креатив не определён».
"""

import bisect
from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.crm import CrmDeal, DealResult
from app.models.meta_ads import MetaAd, MetaAdInsight, MetaFxRate, MetaSyncState
from app.models.user import User
from app.schemas import crm as schemas
from app.services import audit, tz
from app.services.crm.errors import crm_error
from app.services.meta_ads import sync

MAX_DAYS = 366


def _ad_item(ad: MetaAd) -> schemas.AdItem:
    return schemas.AdItem(
        id=ad.id, name=ad.name, status=ad.status, campaign_name=ad.campaign_name, adset_name=ad.adset_name
    )


async def ad_items(db: AsyncSession) -> list[schemas.AdItem]:
    rows = await db.execute(select(MetaAd).order_by(MetaAd.campaign_name, MetaAd.adset_name, MetaAd.name))
    return [_ad_item(ad) for ad in rows.scalars()]


async def ad_item(db: AsyncSession, ad_id: str | None) -> schemas.AdItem | None:
    ad = await db.get(MetaAd, ad_id) if ad_id else None
    return _ad_item(ad) if ad else None


async def status_out(db: AsyncSession) -> schemas.AdsStatus:
    current = await db.get(MetaSyncState, 1)
    return schemas.AdsStatus(
        enabled=settings.meta_enabled,
        synced_at=current.synced_at if current else None,
        error=current.error if current else None,
        error_at=current.error_at if current else None,
        last_day=await db.scalar(select(func.max(MetaAdInsight.day))),
    )


async def rates(db: AsyncSession) -> list[schemas.FxRate]:
    rows = await db.execute(select(MetaFxRate).order_by(MetaFxRate.valid_from.desc()))
    return [schemas.FxRate(valid_from=r.valid_from, rate=float(r.rate)) for r in rows.scalars()]


async def set_rate(db: AsyncSession, user: User, body: schemas.FxRateIn) -> list[schemas.FxRate]:
    row = await db.get(MetaFxRate, body.valid_from, with_for_update=True)
    before = {"rate": float(row.rate)} if row else None
    if row is None:
        row = MetaFxRate(valid_from=body.valid_from, rate=Decimal(str(body.rate)), set_by=user.id)
        db.add(row)
    else:
        row.rate, row.set_by, row.set_at = Decimal(str(body.rate)), user.id, tz.now_utc()
    audit.record(
        db, actor=user, action="crm.ads_rate_set", entity_type="meta_fx_rate", entity_id=body.valid_from.isoformat(),
        before=before, after={"rate": body.rate},
    )
    await db.commit()
    return await rates(db)


async def report(db: AsyncSession, date_from: date, date_to: date) -> schemas.AdsReport:
    if date_to < date_from or (date_to - date_from).days + 1 > MAX_DAYS:
        raise crm_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "period_invalid")

    rate_rows = (await db.execute(select(MetaFxRate.valid_from, MetaFxRate.rate).order_by(MetaFxRate.valid_from))).all()
    rate_days = [r.valid_from for r in rate_rows]

    def rate_on(day: date) -> Decimal | None:
        i = bisect.bisect_right(rate_days, day)
        return rate_rows[i - 1].rate if i else None

    meta: dict[str | None, dict] = defaultdict(lambda: defaultdict(Decimal))
    unrated: set[date] = set()
    for row in (await db.execute(
        select(MetaAdInsight).where(MetaAdInsight.day >= date_from, MetaAdInsight.day <= date_to)
    )).scalars():
        totals = meta[row.ad_id]
        totals["spend_usd"] += row.spend
        rate = rate_on(row.day)
        if rate is None:
            if row.spend:
                unrated.add(row.day)
                totals["unrated"] += 1
        else:
            totals["spend"] += row.spend * rate
        for field in ("impressions", "reach", "clicks", "link_clicks", "conversations"):
            totals[field] += getattr(row, field)

    start, end = tz.day_bounds(date_from)[0], tz.day_bounds(date_to)[1]
    crm: dict[str | None, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for deal in (await db.execute(
        select(CrmDeal).where(CrmDeal.created_at >= start, CrmDeal.created_at < end)
    )).scalars():
        totals = crm[deal.meta_ad_id]
        totals["leads"] += 1
        totals["target"] += deal.is_target is True
        if deal.paid_at is not None:
            totals["paid"] += 1
            totals["revenue"] += deal.paid_amount or 0
        totals["won"] += deal.result == DealResult.won

    ad_ids = {i for i in (*meta, *crm) if i is not None}
    ads = {ad.id: ad for ad in (await db.execute(select(MetaAd).where(MetaAd.id.in_(ad_ids)))).scalars()} if ad_ids else {}

    rows = []
    for ad_id in sorted(ad_ids, key=lambda i: (ads[i].campaign_name or "", ads[i].adset_name or "", ads[i].name) if i in ads else ("", "", i)):
        ad, m, c = ads.get(ad_id), meta.get(ad_id, {}), crm.get(ad_id, {})
        rows.append(schemas.AdRow(
            ad_id=ad_id, ad_name=ad.name if ad else ad_id,
            adset_id=ad.adset_id if ad else None, adset_name=ad.adset_name if ad else None,
            campaign_id=ad.campaign_id if ad else None, campaign_name=ad.campaign_name if ad else None,
            spend_usd=float(m.get("spend_usd", 0)),
            spend=None if m.get("unrated") else int(round(m.get("spend", 0))),
            **{f: int(m.get(f, 0)) for f in ("impressions", "reach", "clicks", "link_clicks", "conversations")},
            **{f: c.get(f, 0) for f in ("leads", "target", "paid", "revenue", "won")},
        ))
    if None in crm:
        c = crm[None]
        rows.append(schemas.AdRow(
            ad_id=None, ad_name=None, adset_id=None, adset_name=None, campaign_id=None, campaign_name=None,
            spend_usd=0, spend=0, impressions=0, reach=0, clicks=0, link_clicks=0, conversations=0,
            **{f: c.get(f, 0) for f in ("leads", "target", "paid", "revenue", "won")},
        ))
    return schemas.AdsReport(
        from_=date_from, to=date_to, rows=rows, days_without_rate=len(unrated), status=await status_out(db),
    )


async def refresh(db: AsyncSession) -> schemas.AdsStatus:
    """«Обновить сейчас»: the last 7 days and the ads list."""
    if not settings.meta_enabled:
        raise crm_error(status.HTTP_404_NOT_FOUND, "meta_disabled")
    try:
        await sync.sync(db, full=True)
    except sync.client.MetaError:
        pass  # recorded on the sync state, shown in the answer
    return await status_out(db)
