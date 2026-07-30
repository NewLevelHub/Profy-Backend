import uuid
from sqlalchemy.orm import InstrumentedAttribute

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_feedback import FeedbackRating, ProductFeedback
from app.models.user import User
from app.schemas.admin import (
    AdminFeedbackListItem,
    AdminFeedbackListResponse,
    AdminFeedbackStatsResponse,
    FeedbackAxisStats,
)
from app.schemas.product_feedback import ProductFeedbackCreateRequest


def _score_to_rating(score: int) -> FeedbackRating:
    """Single source of truth for the good/neutral/bad boundary — used to be
    duplicated on the frontend (useResultFeedback.ts's toRating), which also
    meant the raw 1-5 score never reached the backend at all. Now the score
    is what's stored and averaged; this derived category only feeds the
    existing filter/badge UI in the admin feedback list."""
    if score <= 2:
        return FeedbackRating.bad
    if score == 3:
        return FeedbackRating.neutral
    return FeedbackRating.good


async def has_feedback(
    db: AsyncSession,
    user_id: uuid.UUID,
    assessment_id: uuid.UUID,
    context: str,
) -> bool:
    query = (
        select(ProductFeedback.id)
        .where(
            ProductFeedback.user_id == user_id,
            ProductFeedback.assessment_id == assessment_id,
            ProductFeedback.context == context,
        )
        .limit(1)
    )
    result = await db.execute(query)
    return result.scalar_one_or_none() is not None


async def create_feedback(
    db: AsyncSession,
    user_id: uuid.UUID,
    data: ProductFeedbackCreateRequest,
) -> ProductFeedback:
    feedback = ProductFeedback(
        user_id=user_id,
        assessment_id=data.assessment_id,
        direction_slug=data.direction_slug,
        context=data.context,
        overall_rating=_score_to_rating(data.overall_score),
        overall_score=data.overall_score,
        questions_rating=_score_to_rating(data.questions_score) if data.questions_score is not None else None,
        questions_score=data.questions_score,
        result_match_rating=_score_to_rating(data.result_match_score) if data.result_match_score is not None else None,
        result_match_score=data.result_match_score,
        plan_usefulness_rating=_score_to_rating(data.plan_usefulness_score) if data.plan_usefulness_score is not None else None,
        plan_usefulness_score=data.plan_usefulness_score,
        design_rating=_score_to_rating(data.design_score) if data.design_score is not None else None,
        design_score=data.design_score,
        message=data.message,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return feedback


async def list_feedback(
    db: AsyncSession,
    page: int = 1,
    limit: int = 20,
    rating: str | None = None,
) -> AdminFeedbackListResponse:
    offset = (page - 1) * limit

    query = select(ProductFeedback, User.email).join(User, ProductFeedback.user_id == User.id)
    if rating:
        query = query.where(ProductFeedback.overall_rating == FeedbackRating(rating))

    count_query = select(func.count()).select_from(query.subquery())
    total_count = (await db.execute(count_query)).scalar_one()

    query = query.order_by(ProductFeedback.created_at.desc()).offset(offset).limit(limit)
    rows = (await db.execute(query)).all()

    items = [
        AdminFeedbackListItem(
            id=feedback.id,
            user_id=feedback.user_id,
            user_email=user_email,
            context=feedback.context,
            overall_rating=feedback.overall_rating.value,
            questions_rating=feedback.questions_rating.value if feedback.questions_rating else None,
            result_match_rating=feedback.result_match_rating.value if feedback.result_match_rating else None,
            plan_usefulness_rating=feedback.plan_usefulness_rating.value if feedback.plan_usefulness_rating else None,
            design_rating=feedback.design_rating.value if feedback.design_rating else None,
            overall_score=feedback.overall_score,
            questions_score=feedback.questions_score,
            result_match_score=feedback.result_match_score,
            plan_usefulness_score=feedback.plan_usefulness_score,
            design_score=feedback.design_score,
            message=feedback.message,
            direction_slug=feedback.direction_slug,
            created_at=feedback.created_at,
        )
        for feedback, user_email in rows
    ]

    return AdminFeedbackListResponse(total=total_count, page=page, limit=limit, items=items)


async def _axis_stats(
    db: AsyncSession,
    rating_column: InstrumentedAttribute,
    score_column: InstrumentedAttribute,
) -> FeedbackAxisStats:
    # good/neutral/bad breakdown — present on every row (old rows had only
    # this; new rows get it derived from the score, see _score_to_rating).
    rows = (
        await db.execute(
            select(rating_column, func.count()).where(rating_column.is_not(None)).group_by(rating_column)
        )
    ).all()
    counts = {FeedbackRating.good: 0, FeedbackRating.neutral: 0, FeedbackRating.bad: 0}
    for rating, count in rows:
        counts[rating] = count
    total = sum(counts.values())

    # Real average from the raw score — only rows submitted after the score
    # columns existed have one, so scored_count can be lower than
    # total_count; the frontend shows that explicitly rather than implying
    # every response counted toward the average.
    avg_row = (
        await db.execute(
            select(func.avg(score_column), func.count(score_column)).where(score_column.is_not(None))
        )
    ).one()
    avg_value, scored_count = avg_row
    average = round(float(avg_value), 2) if avg_value is not None else None

    return FeedbackAxisStats(
        average=average,
        good_count=counts[FeedbackRating.good],
        neutral_count=counts[FeedbackRating.neutral],
        bad_count=counts[FeedbackRating.bad],
        total_count=total,
        scored_count=scored_count,
    )


async def get_feedback_stats(db: AsyncSession) -> AdminFeedbackStatsResponse:
    """Aggregated across every feedback row in the table, not just one
    paginated page — list_feedback's `limit`/`page` params are irrelevant
    here on purpose, this always reflects the whole dataset."""
    return AdminFeedbackStatsResponse(
        overall=await _axis_stats(db, ProductFeedback.overall_rating, ProductFeedback.overall_score),
        questions=await _axis_stats(db, ProductFeedback.questions_rating, ProductFeedback.questions_score),
        result_match=await _axis_stats(
            db, ProductFeedback.result_match_rating, ProductFeedback.result_match_score
        ),
        plan_usefulness=await _axis_stats(
            db, ProductFeedback.plan_usefulness_rating, ProductFeedback.plan_usefulness_score
        ),
        design=await _axis_stats(db, ProductFeedback.design_rating, ProductFeedback.design_score),
    )
