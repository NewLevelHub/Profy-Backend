"""Meta ads, as the Marketing API reports them (app/services/meta_ads/).

`meta_ads` is the account's ads with their group and campaign names, renewed
on every sync; `meta_ad_insights` one row per ad per day (Asia/Almaty, the
account's zone), upserted — Meta revises the last days after the fact.
Spend is the account's currency (USD); the CRM turns it into ₸ by the rate
the owner enters (`meta_fx_rates`).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MetaAd(Base):
    __tablename__ = "meta_ads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(400), nullable=False)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    adset_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    adset_name: Mapped[str | None] = mapped_column(String(400), nullable=True)
    campaign_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    campaign_name: Mapped[str | None] = mapped_column(String(400), nullable=True)
    creative_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MetaAdInsight(Base):
    __tablename__ = "meta_ad_insights"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    ad_id: Mapped[str] = mapped_column(String(32), ForeignKey("meta_ads.id", ondelete="CASCADE"), primary_key=True)
    spend: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    reach: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    link_clicks: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # «Начатые переписки» (onsite_conversion.messaging_conversation_started_7d).
    conversations: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MetaFxRate(Base):
    """₸ per 1 USD of ad spend from `valid_from` on, until the next rate (ТЗ
    §3.12.3): the rate the ads were paid at, entered by the owner."""

    __tablename__ = "meta_fx_rates"

    valid_from: Mapped[date] = mapped_column(Date, primary_key=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    set_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MetaSyncState(Base):
    """The last sync — one row, `id = 1` — for «Обновлено …» and the error."""

    __tablename__ = "meta_sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    full_synced_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
