"""Motivation (forced-choice triplets, MOST/LEAST) — scoring + submission.

Category lives on `MotivationStatement`, never duplicated onto
`MotivationResponse` — same normalization discipline as riasec_service /
bigfive_service (response rows store which *statement* was picked, not its
category; category is read via a join/lookup at scoring time)."""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentStatus
from app.models.motivation import MotivationResponse, MotivationStatement
from app.schemas.motivation import MotivationAnswerItem, SubmitMotivationResponse
from app.services import assessment_shared
from scripts.motivation_statement_bank import CATEGORIES as CATEGORY_ORDER

_MOST_POINTS = 2
_NEUTRAL_POINTS = 1
_LEAST_POINTS = 0


async def triplets(db: AsyncSession) -> dict[int, list[MotivationStatement]]:
    result = await db.execute(
        select(MotivationStatement).order_by(
            MotivationStatement.triplet_index, MotivationStatement.order
        )
    )
    grouped: dict[int, list[MotivationStatement]] = {}
    for statement in result.scalars().all():
        grouped.setdefault(statement.triplet_index, []).append(statement)
    return grouped


async def total_triplets(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(func.distinct(MotivationStatement.triplet_index)))
    )
    return result.scalar_one()


async def answered_count(assessment_id: uuid.UUID, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(MotivationResponse.id)).where(
            MotivationResponse.assessment_id == assessment_id
        )
    )
    return result.scalar_one()


async def raw_scores(assessment_id: uuid.UUID, db: AsyncSession) -> dict[str, int]:
    """MOST=2, NEUTRAL(untouched)=1, LEAST=0 per category. Sum over all
    answered triplets always totals 3 points/triplet (methodology-guaranteed,
    not enforced here)."""
    grouped = await triplets(db)
    result = await db.execute(
        select(MotivationResponse).where(MotivationResponse.assessment_id == assessment_id)
    )
    responses = result.scalars().all()

    scores = {c: 0 for c in CATEGORY_ORDER}
    for response in responses:
        for statement in grouped.get(response.triplet_index, []):
            if statement.id == response.most_statement_id:
                scores[statement.category.value] += _MOST_POINTS
            elif statement.id == response.least_statement_id:
                scores[statement.category.value] += _LEAST_POINTS
            else:
                scores[statement.category.value] += _NEUTRAL_POINTS
    return scores


def top_categories(scores: dict[str, int], limit: int = 3) -> list[str]:
    # Tie-break: fixed CATEGORY_ORDER position, same reproducibility rule as
    # riasec_service.top_code / bigfive facet ranking.
    ranked = sorted(CATEGORY_ORDER, key=lambda c: (-scores.get(c, 0), CATEGORY_ORDER.index(c)))
    return ranked[:limit]


async def submit_motivation_answers(
    assessment_id: uuid.UUID,
    answers: list[MotivationAnswerItem],
    current_profile_id: uuid.UUID,
    db: AsyncSession,
) -> SubmitMotivationResponse:
    row_result = await db.execute(select(Assessment).where(Assessment.id == assessment_id))
    assessment = row_result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    if assessment.profile_id != current_profile_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    grouped = await triplets(db)
    for item in answers:
        statements = grouped.get(item.triplet_index)
        if not statements:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown triplet {item.triplet_index}",
            )
        valid_ids = {s.id for s in statements}
        if item.most_statement_id not in valid_ids or item.least_statement_id not in valid_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Statement does not belong to this triplet",
            )
        if item.most_statement_id == item.least_statement_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="most and least must differ"
            )

    is_retake = assessment.status == AssessmentStatus.completed
    if answers:
        stmt = pg_insert(MotivationResponse).values(
            [
                {
                    "id": uuid.uuid4(),
                    "assessment_id": assessment_id,
                    "triplet_index": item.triplet_index,
                    "most_statement_id": item.most_statement_id,
                    "least_statement_id": item.least_statement_id,
                }
                for item in answers
            ]
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_motivation_response_assessment_triplet",
            set_={
                "most_statement_id": stmt.excluded.most_statement_id,
                "least_statement_id": stmt.excluded.least_statement_id,
            },
        )
        await db.execute(stmt)

    if is_retake:
        assessment.status = AssessmentStatus.in_progress
        assessment.completed_at = None
        redis = assessment_shared.get_redis()
        await assessment_shared.invalidate_retake(assessment, db, redis)

    mot_answered = await answered_count(assessment_id, db)
    mot_total = await total_triplets(db)
    mot_completed = mot_total > 0 and mot_answered >= mot_total

    age_group = await assessment_shared.get_profile_age_group(assessment.profile_id, db)
    likert_answered = await assessment_shared.likert_answered_count(assessment_id, db)
    likert_total = await assessment_shared.likert_total_questions(db, age_group)
    likert_completed = likert_total > 0 and likert_answered >= likert_total

    if mot_completed and likert_completed and assessment.status != AssessmentStatus.completed:
        assessment.status = AssessmentStatus.completed
        assessment.completed_at = datetime.now(timezone.utc)

    await db.commit()

    return SubmitMotivationResponse(
        answered_count=mot_answered, total=mot_total, completed=mot_completed
    )
