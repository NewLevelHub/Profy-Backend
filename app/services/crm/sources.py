"""Lead sources (ТЗ §3.2 «Источник»): a list the owner keeps in the CRM, so
the analytics by source is not split by typos. A source is never deleted —
deals refer to it — it is archived: new deals cannot pick it, deals that
have it keep it."""

import uuid

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import CrmSource
from app.models.user import User
from app.schemas import crm as schemas
from app.services import audit
from app.services.crm.errors import crm_error


def _out(source: CrmSource) -> schemas.SourceItem:
    return schemas.SourceItem.model_validate(source, from_attributes=True)


async def _check_unique(db: AsyncSession, name: str, own_id: uuid.UUID | None = None) -> None:
    query = select(CrmSource.id).where(func.lower(CrmSource.name) == name.lower())
    if own_id is not None:
        query = query.where(CrmSource.id != own_id)
    if await db.scalar(query):
        raise crm_error(status.HTTP_409_CONFLICT, "source_exists")


async def create(db: AsyncSession, user: User, body: schemas.SourceIn) -> schemas.SourceItem:
    await _check_unique(db, body.name)
    last = await db.scalar(select(func.max(CrmSource.sort)))
    source = CrmSource(name=body.name, active=True, sort=(last or 0) + 1)
    db.add(source)
    await db.flush()
    audit.record(
        db, actor=user, action="crm.source_created", entity_type="crm_source", entity_id=source.id,
        after={"name": source.name},
    )
    await db.commit()
    return _out(source)


async def update(db: AsyncSession, user: User, source_id: uuid.UUID, body: schemas.SourcePatch) -> schemas.SourceItem:
    source = await db.get(CrmSource, source_id, with_for_update=True)
    if source is None:
        raise crm_error(status.HTTP_404_NOT_FOUND, "source_not_found")
    before = {"name": source.name, "active": source.active}
    if body.name is not None and body.name != source.name:
        await _check_unique(db, body.name, source.id)
        source.name = body.name
    if body.active is not None:
        source.active = body.active
    after = {"name": source.name, "active": source.active}
    if after != before:
        audit.record(
            db, actor=user, action="crm.source_changed", entity_type="crm_source", entity_id=source.id,
            before=before, after=after,
        )
    await db.commit()
    return _out(source)


async def names(db: AsyncSession) -> dict[uuid.UUID, str]:
    return dict((await db.execute(select(CrmSource.id, CrmSource.name))).all())


async def pickable(db: AsyncSession, source_id: uuid.UUID | None, current: uuid.UUID | None = None) -> uuid.UUID | None:
    """A source a deal may be given: an active one (or the one it has)."""
    if source_id is None or source_id == current:
        return source_id
    source = await db.get(CrmSource, source_id)
    if source is None or not source.active:
        raise crm_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "source_not_found")
    return source_id
