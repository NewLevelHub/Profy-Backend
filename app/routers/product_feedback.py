import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.product_feedback import (
    ProductFeedbackCreateRequest,
    ProductFeedbackCreateResponse,
    ProductFeedbackStatusResponse,
)
from app.services import product_feedback_service

router = APIRouter(tags=["product-feedback"])


@router.post("", response_model=ProductFeedbackCreateResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    data: ProductFeedbackCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProductFeedbackCreateResponse:
    await product_feedback_service.create_feedback(db, current_user.id, data)
    return ProductFeedbackCreateResponse()


@router.get("", response_model=ProductFeedbackStatusResponse)
async def get_feedback_status(
    assessment_id: uuid.UUID = Query(...),
    context: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProductFeedbackStatusResponse:
    submitted = await product_feedback_service.has_feedback(db, current_user.id, assessment_id, context)
    return ProductFeedbackStatusResponse(submitted=submitted)
