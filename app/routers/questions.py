import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.question import QuestionBlock
from app.models.user import User
from app.schemas.question import QuestionResponse
from app.services import question_service
from app.services.profile_service import get_profile

router = APIRouter(tags=["questions"])


@router.get("/{assessment_id}/questions/{block}", response_model=list[QuestionResponse])
async def get_block_questions(
    assessment_id: uuid.UUID,
    block: QuestionBlock,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[QuestionResponse]:
    profile = await get_profile(current_user.id, db)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return await question_service.get_questions_for_block(assessment_id, block, profile.id, db)
