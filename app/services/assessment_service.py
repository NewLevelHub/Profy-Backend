import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.profile import Profile
from app.models.question import Question
from app.models.user_response import UserResponse
from app.schemas.assessment import AssessmentResponse
from app.schemas.response import AnswerItem, SubmitAnswersResponse
from app.services import assessment_shared, belbin_service, motivation_service
from app.services.astur import runs as astur_runs


async def _to_response(assessment: Assessment, db: AsyncSession) -> AssessmentResponse:
    answered = await assessment_shared.likert_answered_count(assessment.id, db)
    total = await assessment_shared.likert_total_questions(db)
    mot_answered = await motivation_service.answered_count(assessment.id, db)
    mot_total = await motivation_service.total_triplets(db)

    belbin_run = await belbin_service.get_latest_run(assessment.id, db)
    belbin_completed = belbin_run is not None
    astur_completed = await astur_runs.has_completed_run(db, assessment.id)

    return AssessmentResponse(
        id=assessment.id,
        goal=assessment.goal,
        status=assessment.status,
        answered_count=answered,
        total_questions=total,
        motivation_answered_count=mot_answered,
        motivation_total=mot_total,
        created_at=assessment.created_at,
        secondary_goals=list(assessment.secondary_goals or []),
        goal_changed_count=assessment.goal_changed_count,
        belbin_completed=belbin_completed,
        astur_completed=astur_completed,
    )


async def create_assessment(
    profile_id: uuid.UUID, goal: AssessmentGoal, db: AsyncSession
) -> AssessmentResponse:
    profile_result = await db.execute(select(Profile).where(Profile.id == profile_id))
    profile = profile_result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    existing_result = await db.execute(
        select(Assessment).where(
            Assessment.profile_id == profile_id,
            Assessment.status == AssessmentStatus.in_progress,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        # Discard, don't relabel: stamping an abandoned, possibly-incomplete
        # attempt as `completed` made that status lie — everything else in
        # the codebase (_assert_assessment_complete, /result/generate,
        # get_current_assessment's fallback query) treats `completed` as
        # "this assessment was actually fully answered and can be reported
        # on". An abandoned attempt with e.g. Likert done but motivation
        # never touched isn't that, and previously got stuck exactly there:
        # status said completed, but no AnalysisResult could ever be built.
        # Deleting cascades to its UserResponse/MotivationResponse
        # rows (all FK ondelete="CASCADE") — same
        # "discard stale artifacts on a fresh start" pattern retake
        # invalidation already uses elsewhere in this codebase.
        await db.delete(existing)
        await db.commit()

    assessment = Assessment(
        profile_id=profile_id,
        goal=goal,
        status=AssessmentStatus.in_progress,
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)
    return await _to_response(assessment, db)


async def get_current_assessment(profile_id: uuid.UUID, db: AsyncSession) -> AssessmentResponse | None:
    # Prefer in-progress; fall back to most recent completed so the frontend
    # can restore state after logout without losing the completed assessment.
    result = await db.execute(
        select(Assessment).where(
            Assessment.profile_id == profile_id,
            Assessment.status == AssessmentStatus.in_progress,
        )
    )
    assessment = result.scalar_one_or_none()
    if assessment is None:
        result = await db.execute(
            select(Assessment)
            .where(
                Assessment.profile_id == profile_id,
                Assessment.status == AssessmentStatus.completed,
            )
            .order_by(Assessment.created_at.desc())
            .limit(1)
        )
        assessment = result.scalar_one_or_none()

    if assessment is None:
        return None
    return await _to_response(assessment, db)


async def submit_answers(
    assessment_id: uuid.UUID,
    answers: list[AnswerItem],
    current_profile_id: uuid.UUID,
    db: AsyncSession,
) -> SubmitAnswersResponse:
    row_result = await db.execute(select(Assessment).where(Assessment.id == assessment_id))
    assessment = row_result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    if assessment.profile_id != current_profile_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


    question_ids = [item.question_id for item in answers]
    questions_result = await db.execute(select(Question.id).where(Question.id.in_(question_ids)))
    valid_ids = set(questions_result.scalars().all())
    for item in answers:
        if item.question_id not in valid_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Question {item.question_id} not found",
            )

    is_retake = assessment.status == AssessmentStatus.completed
    if answers:
        stmt = pg_insert(UserResponse).values([
            {
                "id": uuid.uuid4(),
                "assessment_id": assessment_id,
                "question_id": item.question_id,
                "answer_value": item.value,
            }
            for item in answers
        ])
        stmt = stmt.on_conflict_do_update(
            constraint="uq_user_response_assessment_question",
            set_={"answer_value": stmt.excluded.answer_value},
        )
        await db.execute(stmt)

    if is_retake:
        assessment.status = AssessmentStatus.in_progress
        assessment.completed_at = None
        redis = assessment_shared.get_redis()
        await assessment_shared.invalidate_retake(assessment, db, redis)

    answered = await assessment_shared.likert_answered_count(assessment_id, db)
    total = await assessment_shared.likert_total_questions(db)
    # This phase (Likert) being done does NOT mean the whole test is done —
    # the motivation phase may still be pending. assessment.status only
    # flips to completed once motivation_service.submit_motivation_answers
    # confirms both phases are answered (see that function).
    completed = total > 0 and answered >= total

    await db.commit()

    return SubmitAnswersResponse(answered_count=answered, total=total, completed=completed)
