"""CRM deals board and booking (ТЗ CRM Profile v4.1 part 1). Contract:
docs/frontend-crm-api-contract.md.

Mounted at `/api/v1/crm`. Sales roles only; the marketer reads the board
without personal data and cannot open or change a deal (ТЗ §2).
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.user import User, UserRole
from app.schemas import crm as schemas
from app.services.crm import deals

router = APIRouter(tags=["crm"])

_board_reader = require_role(UserRole.owner, UserRole.sales_head, UserRole.sales_manager, UserRole.marketer)
_seller = require_role(UserRole.owner, UserRole.sales_head, UserRole.sales_manager)


async def _detail(db: AsyncSession, user: User, deal_id: uuid.UUID) -> schemas.DealDetail:
    return await deals.detail(db, user, await deals.get_deal(db, user, deal_id))


@router.get("/meta", response_model=schemas.CrmMeta)
async def meta(_: User = Depends(_board_reader), db: AsyncSession = Depends(get_db)) -> schemas.CrmMeta:
    return await deals.meta(db)


@router.get("/deals", response_model=list[schemas.DealCard])
async def list_deals(
    result: Literal["open", "won", "lost", "all"] = Query(default="open"),
    user: User = Depends(_board_reader),
    db: AsyncSession = Depends(get_db),
) -> list[schemas.DealCard]:
    return await deals.list_deals(db, user, result)


@router.post("/deals", response_model=schemas.DealDetail, status_code=201)
async def create_deal(
    body: schemas.DealCreate, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    deal = await deals.create_deal(db, user, body)
    return await _detail(db, user, deal.id)


@router.get("/parents", response_model=list[schemas.ParentMatch])
async def find_parents(
    phone: str = Query(max_length=32), _: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> list[schemas.ParentMatch]:
    return await deals.find_parents(db, phone)


@router.get("/deals/{deal_id}", response_model=schemas.DealDetail)
async def get_deal(
    deal_id: uuid.UUID, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    return await _detail(db, user, deal_id)


@router.patch("/deals/{deal_id}", response_model=schemas.DealDetail)
async def patch_deal(
    deal_id: uuid.UUID, body: schemas.DealPatch, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    await deals.patch_deal(db, user, deal_id, body)
    return await _detail(db, user, deal_id)


@router.post("/deals/{deal_id}/accept", response_model=schemas.DealDetail)
async def accept(deal_id: uuid.UUID, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)):
    await deals.accept(db, user, deal_id)
    return await _detail(db, user, deal_id)


@router.post("/deals/{deal_id}/stage", response_model=schemas.DealDetail)
async def move(
    deal_id: uuid.UUID, body: schemas.StageMove, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    await deals.move(db, user, deal_id, body.stage)
    return await _detail(db, user, deal_id)


@router.post("/deals/{deal_id}/payment", response_model=schemas.DealDetail)
async def mark_payment(
    deal_id: uuid.UUID, body: schemas.PaymentIn, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    await deals.mark_payment(db, user, deal_id, body)
    return await _detail(db, user, deal_id)


@router.delete("/deals/{deal_id}/payment", response_model=schemas.DealDetail)
async def cancel_payment(
    deal_id: uuid.UUID, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    await deals.cancel_payment(db, user, deal_id)
    return await _detail(db, user, deal_id)


@router.post("/deals/{deal_id}/consent", response_model=schemas.DealDetail)
async def set_consent(
    deal_id: uuid.UUID, body: schemas.ConsentIn, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    await deals.set_consent(db, user, deal_id, body.given)
    return await _detail(db, user, deal_id)


@router.post("/deals/{deal_id}/close", response_model=schemas.DealDetail)
async def close(
    deal_id: uuid.UUID, body: schemas.CloseIn, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    await deals.close(db, user, deal_id, body)
    return await _detail(db, user, deal_id)


@router.post("/deals/{deal_id}/notes", response_model=schemas.DealDetail)
async def add_note(
    deal_id: uuid.UUID, body: schemas.NoteIn, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    await deals.add_note(db, user, deal_id, body.text)
    return await _detail(db, user, deal_id)


@router.post("/deals/{deal_id}/booking", response_model=schemas.DealDetail)
async def book(
    deal_id: uuid.UUID, body: schemas.BookingIn, user: User = Depends(_seller), db: AsyncSession = Depends(get_db)
) -> schemas.DealDetail:
    await deals.book(db, user, deal_id, body)
    return await _detail(db, user, deal_id)
