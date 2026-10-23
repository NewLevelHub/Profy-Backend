"""The price list (ТЗ §3.7): the owner adds tariffs and changes their terms
in the CRM. A tariff is never deleted — deals refer to it — it is archived:
new deals cannot pick it, deals that have it keep it.

«Консультация и проверка отчёта психологом» (`psychologist_review`): the
manager books a 30-minute first call, the specialist sets the 60-minute
second one (app/services/scheduling/second_meeting.py). A tariff without it
has no calls and the report goes to the student at once.

A deal keeps the price of the day its tariff was picked, and whether a
psychologist reviews the report: a change only applies to deals that pick
the tariff afterwards.
"""

import secrets

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import CrmTariff
from app.models.user import User
from app.schemas import crm as schemas
from app.services import audit
from app.services.crm.deals import crm_error

_FIELDS = ("name", "price", "description", "psychologist_review", "active")
# Explicit null is a valid value only here; the rest keep their value.
_NULLABLE = {"description"}


def _snapshot(tariff: CrmTariff) -> dict:
    return {field: getattr(tariff, field) for field in _FIELDS}


def _out(tariff: CrmTariff) -> schemas.TariffItem:
    return schemas.TariffItem.model_validate(tariff, from_attributes=True)


def _clean(description: str | None) -> str | None:
    return (description or "").strip() or None


async def create(db: AsyncSession, user: User, body: schemas.TariffIn) -> schemas.TariffItem:
    last = await db.scalar(select(func.max(CrmTariff.sort)))
    tariff = CrmTariff(
        code=f"t_{secrets.token_hex(6)}",
        name=body.name,
        price=body.price,
        description=_clean(body.description),
        psychologist_review=body.psychologist_review,
        active=True,
        sort=(last or 0) + 1,
    )
    db.add(tariff)
    audit.record(
        db, actor=user, action="crm.tariff_created", entity_type="crm_tariff", entity_id=tariff.code,
        after=_snapshot(tariff),
    )
    await db.commit()
    return _out(tariff)


async def update(db: AsyncSession, user: User, code: str, body: schemas.TariffPatch) -> schemas.TariffItem:
    tariff = await db.scalar(select(CrmTariff).where(CrmTariff.code == code).with_for_update())
    if tariff is None:
        raise crm_error(status.HTTP_404_NOT_FOUND, "tariff_not_found")
    before = _snapshot(tariff)
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None and field not in _NULLABLE:
            continue
        if field == "description":
            value = _clean(value)
        setattr(tariff, field, value)
    after = _snapshot(tariff)
    if after != before:
        audit.record(
            db, actor=user, action="crm.tariff_changed", entity_type="crm_tariff", entity_id=tariff.code,
            before={k: v for k, v in before.items() if v != after[k]},
            after={k: v for k, v in after.items() if v != before[k]},
        )
    await db.commit()
    return _out(tariff)
