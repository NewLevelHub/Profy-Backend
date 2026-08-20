import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_feedback import ProductFeedback
from app.schemas.feedback import ProductFeedbackCreate, ProductFeedbackResponse


async def submit_feedback(
    user_id: uuid.UUID,
    data: ProductFeedbackCreate,
    db: AsyncSession,
) -> ProductFeedbackResponse:
    """Store a post-report feedback submission. Assessment ownership is
    already verified by the caller (router's `_require_assessment_access`,
    same check every other /result endpoint uses) before this runs."""
    feedback = ProductFeedback(
        user_id=user_id,
        assessment_id=data.assessment_id,
        relevance_score=data.relevance_score,
        helpful_sections=data.helpful_sections,
        comment=data.comment,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    return ProductFeedbackResponse(
        id=feedback.id,
        assessment_id=feedback.assessment_id,
        relevance_score=feedback.relevance_score,
        helpful_sections=list(feedback.helpful_sections),
        comment=feedback.comment,
        created_at=feedback.created_at,
    )
