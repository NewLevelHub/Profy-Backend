import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.assessment import AssessmentStatus
from app.models.user import User
from app.schemas.assessment import AssessmentCreateRequest, AssessmentResponse
from app.schemas.report import DirectionMatch, ReportResponse
from app.schemas.response import SaveAnswersRequest, SaveAnswersResponse
from app.services import assessment_service
from app.services import scoring_service
from app.services.profile_service import get_profile
from app.services.ai_service import build_strengths

router = APIRouter(tags=["assessment"])


async def _require_profile_id(current_user: User, db: AsyncSession) -> uuid.UUID:
    profile = await get_profile(current_user.id, db)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile.id


@router.post("/start", response_model=AssessmentResponse)
async def start_assessment(
    data: AssessmentCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssessmentResponse:
    profile_id = await _require_profile_id(current_user, db)
    return await assessment_service.create_assessment(profile_id, data.goal, db)


@router.get("/current", response_model=AssessmentResponse)
async def get_current_assessment(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssessmentResponse:
    profile_id = await _require_profile_id(current_user, db)
    assessment = await assessment_service.get_current_assessment(profile_id, db)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active assessment found")
    return assessment


@router.post("/{assessment_id}/report", response_model=ReportResponse)
async def generate_report(
    assessment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    from sqlalchemy import select
    from app.models.assessment import Assessment
    from app.models.profile import Profile

    row_result = await db.execute(
        select(Assessment, Profile.id)
        .join(Profile, Assessment.profile_id == Profile.id)
        .where(Assessment.id == assessment_id)
    )
    row = row_result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    assessment, profile_id = row
    profile_result = await db.execute(select(Profile).where(Profile.id == profile_id))
    profile = profile_result.scalar_one_or_none()
    if profile is None or profile.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    normalized = await assessment_service.get_total_scores(assessment_id, db)
    strengths = build_strengths(normalized)
    raw_directions = scoring_service.match_directions(normalized)
    directions = [DirectionMatch(direction=d["direction"], score=d["score"]) for d in raw_directions]

    return ReportResponse(
        assessment_id=str(assessment_id),
        normalized_scores=normalized,
        strengths=strengths,
        directions=directions,
    )


@router.post("/{assessment_id}/answers", response_model=SaveAnswersResponse)
async def submit_answers(
    assessment_id: uuid.UUID,
    data: SaveAnswersRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SaveAnswersResponse:
    profile_id = await _require_profile_id(current_user, db)
    scores = await assessment_service.complete_block(
        assessment_id, data.block, data.answers, profile_id, db
    )
    return SaveAnswersResponse(block=data.block, scores=scores)
