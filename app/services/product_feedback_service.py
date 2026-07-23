import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_feedback import FeedbackRating, ProductFeedback
from app.models.user import User
from app.schemas.admin import AdminFeedbackListItem, AdminFeedbackListResponse
from app.schemas.product_feedback import ProductFeedbackCreateRequest


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
        rating=FeedbackRating(data.rating),
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
        query = query.where(ProductFeedback.rating == FeedbackRating(rating))

    count_query = select(func.count()).select_from(query.subquery())
    total_count = (await db.execute(count_query)).scalar_one()

    query = query.order_by(ProductFeedback.created_at.desc()).offset(offset).limit(limit)
    rows = (await db.execute(query)).all()

    items = [
        AdminFeedbackListItem(
            id=feedback.id,
            user_email=user_email,
            context=feedback.context,
            rating=feedback.rating.value,
            message=feedback.message,
            direction_slug=feedback.direction_slug,
            created_at=feedback.created_at,
        )
        for feedback, user_email in rows
    ]

    return AdminFeedbackListResponse(total=total_count, page=page, limit=limit, items=items)
