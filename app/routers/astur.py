import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.services import astur_service

router = APIRouter(tags=["astur"])


@router.get("/astur/content", response_model=AsturContentResponse)
async def get_astur_content(
    current_user: User = Depends(get_current_user),
) -> AsturContentResponse:
    """PRO-338 Ф3.6 prerequisite — static content, same for every user, no
    `assessment_id` in the path (unlike start/submit): the frontend fetches
    this once to render all 7 subtests, independent of which assessment
    the eventual submits target. Mirrors Ф2.6's own `GET .../belbin/content`
    gap-fix for the same reason: nothing exposed item text before this."""
    return AsturContentResponse(**astur_service.build_content())


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
    return SubmitAsturSubtestResponse(
        run_id=run.id, subtest=key, actual_ms=actual_ms, over_limit_items=over_limit_items
    )
