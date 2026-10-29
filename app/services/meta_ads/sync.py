"""Ads data from Meta into the CRM (doc «Meta Marketing API — подключение»,
§5). Every hour: today and yesterday — Meta keeps adding to them for ~48 h.
Once a day, the first run after midnight (Almaty): the last 7 days, for late
corrections and the 7-day attribution window, and the ads list (names
change). The very first run takes `HISTORY_DAYS` back. Rows are upserted by
(day, ad), so a run can repeat at no cost.

`run_sync_loop` runs in the API process (`app.main.lifespan`) only while the
token is configured; «Обновить сейчас» in the CRM calls `sync` directly.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.meta_ads import MetaAd, MetaAdInsight, MetaSyncState
from app.services import tz
from app.services.crm import lead_source
from app.services.meta_ads import client

logger = logging.getLogger(__name__)

DAILY_DAYS = 7
HISTORY_DAYS = 90
# One sync at a time: the loop and «Обновить сейчас» share the process.
_lock = asyncio.Lock()


async def state(db: AsyncSession) -> MetaSyncState:
    row = await db.get(MetaSyncState, 1)
    if row is None:
        row = MetaSyncState(id=1)
        db.add(row)
        await db.flush()
    return row


def _int(value) -> int:
    return int(float(value or 0))


async def _upsert_ads(db: AsyncSession, rows: list[dict]) -> None:
    for row in rows:
        values = {
            "id": row["id"],
            "name": row.get("name") or row["id"],
            "status": row.get("status"),
            "adset_id": row.get("adset_id"),
            "adset_name": (row.get("adset") or {}).get("name"),
            "campaign_id": row.get("campaign_id"),
            "campaign_name": (row.get("campaign") or {}).get("name"),
            "creative_id": (row.get("creative") or {}).get("id"),
        }
        await db.execute(
            insert(MetaAd).values(**values).on_conflict_do_update(
                index_elements=[MetaAd.id], set_={**values, "updated_at": func.now()}
            )
        )


async def _upsert_insights(db: AsyncSession, rows: list[dict]) -> int:
    for row in rows:
        ad = {
            "id": row["ad_id"],
            "name": row.get("ad_name") or row["ad_id"],
            "adset_id": row.get("adset_id"),
            "adset_name": row.get("adset_name"),
            "campaign_id": row.get("campaign_id"),
            "campaign_name": row.get("campaign_name"),
        }
        # An ad only seen in the insights (deleted since) still gets its names.
        await db.execute(
            insert(MetaAd).values(**ad).on_conflict_do_update(
                index_elements=[MetaAd.id],
                set_={k: v for k, v in ad.items() if k != "id" and v is not None},
            )
        )
        values = {
            "day": date.fromisoformat(row["date_start"]),
            "ad_id": row["ad_id"],
            "spend": Decimal(str(row.get("spend") or "0")),
            "impressions": _int(row.get("impressions")),
            "reach": _int(row.get("reach")),
            "clicks": _int(row.get("clicks")),
            "link_clicks": _int(row.get("inline_link_clicks")),
            "conversations": client.conversations(row),
        }
        await db.execute(
            insert(MetaAdInsight).values(**values).on_conflict_do_update(
                index_elements=[MetaAdInsight.day, MetaAdInsight.ad_id],
                set_={**{k: v for k, v in values.items() if k not in ("day", "ad_id")}, "synced_at": func.now()},
            )
        )
    return len(rows)


async def sync(db: AsyncSession, now: datetime | None = None, *, full: bool = False) -> int:
    """Pull what is due; the number of daily rows written. A Graph API
    refusal is recorded on the sync state (shown in the CRM) and re-raised."""
    now = now or tz.now_utc()
    today = tz.today(now)
    async with _lock:
        current = await state(db)
        first = await db.scalar(select(func.count()).select_from(MetaAdInsight)) == 0
        daily = full or current.full_synced_on != today
        days = HISTORY_DAYS if first else DAILY_DAYS if daily else 2
        try:
            if daily:
                await _upsert_ads(db, await client.ads())
            written = await _upsert_insights(db, await client.insights(today - timedelta(days=days - 1), today))
        except client.MetaError as error:
            await db.rollback()
            current = await state(db)
            current.error = f"{error.code}: {error}" if error.code else str(error)
            current.error_at = now
            await db.commit()
            raise
        current.synced_at = now
        if daily:
            current.full_synced_on = today
        current.error = current.error_at = None
        # WhatsApp leads that came from an ad unknown until this sync.
        await lead_source.attach_late_ads(db)
        await db.commit()
        return written


async def run_sync_loop() -> None:
    while True:
        try:
            async with async_session() as db:
                written = await sync(db)
            logger.info("Meta ads synced: %s daily rows", written)
        except asyncio.CancelledError:
            raise
        except client.MetaError as error:
            logger.warning("Meta ads sync refused (code %s)", error.code)
        except Exception:
            logger.exception("Meta ads sync failed")
        await asyncio.sleep(settings.META_SYNC_INTERVAL_SECONDS)
