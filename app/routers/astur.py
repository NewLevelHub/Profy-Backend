import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n.catalog import key as i18n_key
from app.database import get_db
from app.dependencies import get_current_user
from app.models.assessment import Assessment
from app.models.profile import Profile
from app.models.user import User
from app.schemas.astur import (
    AsturContentResponse,
    StartAsturSubtestResponse,
    SubmitAsturSubtestRequest,
    SubmitAsturSubtestResponse,
)
from app.services import assessment_shared, astur_service

router = APIRouter(tags=["astur"])
logger = logging.getLogger(__name__)


@router.get("/astur/content", response_model=AsturContentResponse)
async def get_astur_content(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AsturContentResponse:
    """PRO-338 Ф3.6 prerequisite — static content, same for every user, no
    `assessment_id` in the path (unlike start/submit): the frontend fetches
    this once to render all 7 subtests, independent of which assessment
    the eventual submits target. Mirrors Ф2.6's own `GET .../belbin/content`
    gap-fix for the same reason: nothing exposed item text before this."""
    try:
        return AsturContentResponse(**await astur_service.build_content(db))
    except (ValidationError, TypeError, AttributeError):
        # An admin content override with a bad shape must not take the
        # whole test down for every real test-taker — fall back to the
        # bank's own content until the override is fixed.
        logger.exception("Malformed ASTUR content override, falling back to bank default")
        return AsturContentResponse(**await astur_service.build_content(db, ignore_override=True))


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
            status_code=status.HTTP_404_NOT_FOUND, detail=i18n_key("api_errors", "assessment_not_found", locale="ru")
        )
    if row.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=i18n_key("api_errors", "access_denied", locale="ru")
        )


@router.post(
    "/{assessment_id}/astur/subtest/{n}/start",
    response_model=StartAsturSubtestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_astur_subtest(
    assessment_id: uuid.UUID,
    n: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StartAsturSubtestResponse:
    """Опциональный блок вне основного потока (04-Фаза3-АСТУР.md, запуск
    из кабинета психолога) — субтесты 1-2, 4-7: сервер фиксирует
    started_at, не доверяя клиентскому таймеру полностью (Ф3.4)."""
    await _require_owned_assessment(assessment_id, current_user, db)
    run, key, started_at = await astur_service.start_subtest(
        assessment_id, n, user_id=current_user.id, db=db
    )
    return StartAsturSubtestResponse(run_id=run.id, subtest=key, started_at=started_at)


@router.post(
    "/{assessment_id}/astur/subtest/{n}",
    response_model=SubmitAsturSubtestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_astur_subtest(
    assessment_id: uuid.UUID,
    n: int,
    data: SubmitAsturSubtestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubmitAsturSubtestResponse:
    """Per-subtest submit — предпочтён единому сабмиту, чтобы длинный тест
    не терял прогресс при обрыве связи (Ф3.4). Продолжает текущую попытку
    (та же строка `astur_runs`), пока она не завершена полностью; после
    завершения следующий сабмит начинает новую попытку (append-only,
    Ф3.3)."""
    await _require_owned_assessment(assessment_id, current_user, db)
    run, key, actual_ms, over_limit_items = await astur_service.submit_subtest(
        assessment_id, n, data.answers, data.elapsed_ms, user_id=current_user.id, db=db
    )

    # АСТУР is the last phase in the continuous flow (motivation -> Belbin ->
    # АСТУР) — this is where `assessment.status` actually gets to flip to
    # `completed`, since Likert/motivation were already done earlier but
    # Belbin/АСТУР weren't yet (see assessment_shared.try_complete_assessment).
    if astur_service.is_complete(run):
        assessment_row = (
            await db.execute(select(Assessment).where(Assessment.id == assessment_id))
        ).scalar_one()
        likert_answered = await assessment_shared.likert_answered_count(assessment_id, db)
        likert_total = await assessment_shared.likert_total_questions(db)
        likert_completed = likert_total > 0 and likert_answered >= likert_total
        motivation_completed = await assessment_shared.motivation_completed(assessment_id, db)
        if await assessment_shared.try_complete_assessment(
            assessment_row,
            likert_completed=likert_completed,
            motivation_completed=motivation_completed,
            db=db,
        ):
            await db.commit()

    return SubmitAsturSubtestResponse(
        run_id=run.id, subtest=key, actual_ms=actual_ms, over_limit_items=over_limit_items
    )
