import uuid

from fastapi import APIRouter, Depends, HTTPException, status
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
    AsturRunSummary,
    AsturStateResponse,
    StartAsturSubtestResponse,
    SubmitAsturSubtestRequest,
    SubmitAsturSubtestResponse,
)
from app.services import assessment_shared
from app.services.astur import runs

router = APIRouter(tags=["astur"])


async def _require_owned_assessment(assessment_id: uuid.UUID, current_user: User, db: AsyncSession) -> None:
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


@router.get("/{assessment_id}/astur/state", response_model=AsturStateResponse)
async def get_astur_state(
    assessment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AsturStateResponse:
    """Not started / in progress (with submitted subtests, to resume) /
    completed. The open attempt and the last completed one are reported
    separately — an open retake never hides a finished result."""
    await _require_owned_assessment(assessment_id, current_user, db)
    return AsturStateResponse(**await runs.get_state(db, assessment_id))


@router.post(
    "/{assessment_id}/astur/runs", response_model=AsturRunSummary, status_code=status.HTTP_201_CREATED
)
async def start_astur_retake(
    assessment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AsturRunSummary:
    """Explicit «Пройти заново»: opens a new attempt on the latest published
    bank version. Idempotent while an attempt is open."""
    await _require_owned_assessment(assessment_id, current_user, db)
    run = await runs.start_retake(db, assessment_id, user_id=current_user.id)
    return AsturRunSummary(**await runs.run_summary(db, run))


@router.get("/{assessment_id}/astur/content", response_model=AsturContentResponse)
async def get_astur_content(
    assessment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AsturContentResponse:
    """Content of the bank version the open attempt is pinned to, so the
    questions shown are always the ones scored with their own keys."""
    await _require_owned_assessment(assessment_id, current_user, db)
    return AsturContentResponse(**await runs.content_for(db, assessment_id))


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
    await _require_owned_assessment(assessment_id, current_user, db)
    run, key, started_at = await runs.start_subtest(db, assessment_id, n, user_id=current_user.id)
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
    """Per-subtest submit into the open attempt (a dropped connection never
    loses earlier subtests). The submit that completes the attempt freezes
    its result; a completed attempt answers 409 `astur_attempt_completed`."""
    await _require_owned_assessment(assessment_id, current_user, db)
    run, key, actual_ms, over_limit_items, completed = await runs.submit_subtest(
        db, assessment_id, n, data.answers,
        elapsed_ms=data.elapsed_ms, client_timezone=data.client_timezone, user_id=current_user.id,
    )

    # АСТУР is the last phase of the continuous flow — its completion is
    # where the assessment itself can flip to `completed`.
    if completed:
        assessment_row = (await db.execute(select(Assessment).where(Assessment.id == assessment_id))).scalar_one()
        likert_answered = await assessment_shared.likert_answered_count(assessment_id, db)
        likert_total = await assessment_shared.likert_total_questions(db)
        if await assessment_shared.try_complete_assessment(
            assessment_row,
            likert_completed=likert_total > 0 and likert_answered >= likert_total,
            motivation_completed=await assessment_shared.motivation_completed(assessment_id, db),
            db=db,
        ):
            await db.commit()

    return SubmitAsturSubtestResponse(
        run_id=run.id, subtest=key, actual_ms=actual_ms,
        over_limit_items=over_limit_items, run_completed=completed,
    )
