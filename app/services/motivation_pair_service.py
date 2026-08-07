"""Motivation (Harter-format pairs) — junior/middle's alternative to the
3-way MOST/LEAST triplet mechanic (app/services/motivation_service.py,
which senior keeps using unchanged). "Some kids like X, but other kids
[prefer] Y" -> pick a camp -> rate intensity ("Точно про меня" / "Немного
про меня"). Mirrors motivation_service.py's shape (pairs/total/answered/
raw_scores/submit) so report_service.py can call whichever one matches the
profile's age_group."""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentStatus
from app.models.motivation_pair import MotivationIntensity, MotivationPair, MotivationPairResponse
from app.schemas.motivation_pair import MotivationPairItem, PairIntensityAnswer, SubmitMotivationPairResponse
from app.services import assessment_shared
from scripts.motivation_statement_bank import CATEGORIES as CATEGORY_ORDER

_HIGH_CHOSEN_POINTS = 2
_HIGH_OTHER_POINTS = 0
_MEDIUM_CHOSEN_POINTS = 1
_MEDIUM_OTHER_POINTS = 1


async def pairs(db: AsyncSession) -> list[MotivationPair]:
    result = await db.execute(select(MotivationPair).order_by(MotivationPair.pair_index))
    return list(result.scalars().all())


async def total_pairs(db: AsyncSession) -> int:
    result = await db.execute(select(func.count(MotivationPair.id)))
    return result.scalar_one()


async def answered_count(assessment_id: uuid.UUID, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(MotivationPairResponse.id)).where(
            MotivationPairResponse.assessment_id == assessment_id
        )
    )
    return result.scalar_one()


async def raw_scores(assessment_id: uuid.UUID, db: AsyncSession) -> dict[str, int]:
    pairs_by_index = {p.pair_index: p for p in await pairs(db)}
    result = await db.execute(
        select(MotivationPairResponse).where(MotivationPairResponse.assessment_id == assessment_id)
    )
    responses = result.scalars().all()

    scores = {c: 0 for c in CATEGORY_ORDER}
    for response in responses:
        pair = pairs_by_index.get(response.pair_index)
        if pair is None:
            continue
        other_category = (
            pair.category_b.value if response.chosen_category == pair.category_a else pair.category_a.value
        )
        if response.intensity == MotivationIntensity.high:
            scores[response.chosen_category.value] += _HIGH_CHOSEN_POINTS
            scores[other_category] += _HIGH_OTHER_POINTS
        else:
            scores[response.chosen_category.value] += _MEDIUM_CHOSEN_POINTS
            scores[other_category] += _MEDIUM_OTHER_POINTS
    return scores


async def submit_pair_answers(
    assessment_id: uuid.UUID,
    answers: list[PairIntensityAnswer],
    current_profile_id: uuid.UUID,
    db: AsyncSession,
) -> SubmitMotivationPairResponse:
    row_result = await db.execute(select(Assessment).where(Assessment.id == assessment_id))
    assessment = row_result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    if assessment.profile_id != current_profile_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    pairs_by_index = {p.pair_index: p for p in await pairs(db)}

    response_rows: list[dict] = []
    for item in answers:
        pair = pairs_by_index.get(item.pair_index)
        if pair is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown pair {item.pair_index}",
            )
        chosen_category = pair.category_a if item.chosen_side == "a" else pair.category_b
        response_rows.append({
            "id": uuid.uuid4(),
            "assessment_id": assessment_id,
            "pair_index": item.pair_index,
            "chosen_category": chosen_category,
            "intensity": MotivationIntensity(item.intensity),
        })

    is_retake = assessment.status == AssessmentStatus.completed
    if response_rows:
        stmt = pg_insert(MotivationPairResponse).values(response_rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_motivation_pair_response_assessment_pair",
            set_={
                "chosen_category": stmt.excluded.chosen_category,
                "intensity": stmt.excluded.intensity,
            },
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

    mot_answered = await answered_count(assessment_id, db)
    mot_total = await total_pairs(db)
    mot_completed = mot_total > 0 and mot_answered >= mot_total

    age_group = await assessment_shared.get_profile_age_group(assessment.profile_id, db)
    likert_answered = await assessment_shared.likert_answered_count(assessment_id, db)
    likert_total = await assessment_shared.likert_total_questions(db, age_group)
    likert_completed = likert_total > 0 and likert_answered >= likert_total

    if mot_completed and likert_completed and assessment.status != AssessmentStatus.completed:
        assessment.status = AssessmentStatus.completed
        assessment.completed_at = datetime.now(timezone.utc)

    await db.commit()

    return SubmitMotivationPairResponse(
        answered_count=mot_answered, total=mot_total, completed=mot_completed
    )
