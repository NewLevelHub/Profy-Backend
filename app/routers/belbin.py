import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.i18n import MissingLocalizedText, pick_locale
from app.models.assessment import Assessment
from app.models.profile import Profile
from app.models.user import User
from app.schemas.belbin import (
    BelbinContentResponse,
    SubmitBelbinRequest,
    SubmitBelbinResponse,
)
from app.services import belbin_service
from scripts.belbin_bank import BLOCK_TOTAL, INSTRUCTION, SECTIONS

router = APIRouter(tags=["belbin"])
logger = logging.getLogger(__name__)


@router.get("/belbin/content", response_model=BelbinContentResponse)
async def get_belbin_content(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BelbinContentResponse:
    """PRO-338 Ф2.6 prerequisite — static content, same for every user, no
    `assessment_id` in the path (unlike submit): the frontend fetches this
    once to render the 7-block flow, independent of which assessment the
    eventual submit targets."""
    try:
        return BelbinContentResponse(**await belbin_service.build_content(db))
    except (ValidationError, TypeError, AttributeError, MissingLocalizedText):
        # An admin content override with a bad or incomplete shape must not
        # take the whole test down for every real test-taker — fall back to
        # the bank's own content until the override is fixed.
        logger.exception("Malformed Belbin content override, falling back to bank default")
        return BelbinContentResponse(**await belbin_service.build_content(db, ignore_override=True))


async def _require_owned_assessment(
    assessment_id: uuid.UUID, current_user: User, db: AsyncSession
) -> None:
    row = (
        await db.execute(
            select(Assessment.id, Profile.user_id)
            .join(Profile, Assessment.profile_id == Profile.id)
            .where(Assessment.id == assessment_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found"
        )
    if row.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )


@router.post(
    "/{assessment_id}/belbin",
    response_model=SubmitBelbinResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_belbin(
    assessment_id: uuid.UUID,
    data: SubmitBelbinRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubmitBelbinResponse:
    """Опциональный блок вне основного потока (03-Фаза2-Белбин.md,
    запускается из кабинета психолога) — один вызов, 7 блоков × 8 значений,
    сумма строго 10 на блок (422 иначе), Σ по 8 ролям сразу при сабмите."""
    await _require_owned_assessment(assessment_id, current_user, db)
    run = await belbin_service.submit_run(
        assessment_id, data.allocations, user_id=current_user.id, db=db
    )
    return SubmitBelbinResponse(run_id=run.id, role_totals=run.role_totals)
