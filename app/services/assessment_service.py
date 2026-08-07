import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.profile import AgeGroup, Profile
from app.models.question import Question
from app.models.user_response import UserResponse
from app.schemas.assessment import AssessmentResponse
from app.schemas.response import AnswerItem, SubmitAnswersResponse
from app.services import assessment_shared, motivation_pair_service, motivation_service, riasec_service


async def _to_response(assessment: Assessment, db: AsyncSession) -> AssessmentResponse:
    age_group = await assessment_shared.get_profile_age_group(assessment.profile_id, db)
    answered = await assessment_shared.likert_answered_count(assessment.id, db)
    total = await assessment_shared.likert_total_questions(db, age_group)
    # Junior/middle answer the Harter-format pairs instead of the 3-way
    # MOST/LEAST triplets (senior) — different tables, see motivation_pair_service.py.
    if age_group in (AgeGroup.junior, AgeGroup.middle):
        mot_answered = await motivation_pair_service.answered_count(assessment.id, db)
        mot_total = await motivation_pair_service.total_pairs(db)
    else:
        mot_answered = await motivation_service.answered_count(assessment.id, db)
        mot_total = await motivation_service.total_triplets(db)
    return AssessmentResponse(
        id=assessment.id,
        goal=assessment.goal,
        status=assessment.status,
        answered_count=answered,
        total_questions=total,
        motivation_answered_count=mot_answered,
        motivation_total=mot_total,
        created_at=assessment.created_at,
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
        existing.status = AssessmentStatus.completed
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

    age_group = await assessment_shared.get_profile_age_group(assessment.profile_id, db)

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

        old_result = await db.execute(
            select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
        )
        old_analysis = old_result.scalar_one_or_none()
        if old_analysis is not None:
            await db.delete(old_analysis)
        redis = assessment_shared.get_redis()
        await redis.delete(f"report:{assessment_id}")
        await assessment_shared.invalidate_direction_flow(assessment, db, redis)
        await assessment_shared.invalidate_goal_roadmap(assessment_id, db, redis)

    answered = await assessment_shared.likert_answered_count(assessment_id, db)
    total = await assessment_shared.likert_total_questions(db, age_group)
    # This phase (Likert) being done does NOT mean the whole test is done —
    # the motivation phase may still be pending. assessment.status only
    # flips to completed once motivation_service.submit_motivation_answers
    # confirms both phases are answered (see that function).
    completed = total > 0 and answered >= total

    await db.commit()

    return SubmitAnswersResponse(answered_count=answered, total=total, completed=completed)


async def _age_group_for_assessment(assessment_id: uuid.UUID, db: AsyncSession) -> AgeGroup:
    result = await db.execute(
        select(Profile.age_group)
        .join(Assessment, Assessment.profile_id == Profile.id)
        .where(Assessment.id == assessment_id)
    )
    return result.scalar_one()


async def get_raw_scores(assessment_id: uuid.UUID, db: AsyncSession) -> dict[str, int]:
    age_group = await _age_group_for_assessment(assessment_id, db)
    return await riasec_service.raw_scores(assessment_id, db, age_group)


async def get_total_scores(assessment_id: uuid.UUID, db: AsyncSession) -> dict[str, float]:
    age_group = await _age_group_for_assessment(assessment_id, db)
    raw = await riasec_service.raw_scores(assessment_id, db, age_group)
    counts = await riasec_service.question_counts(db, age_group)
    return riasec_service.normalize(raw, counts)
