"""Student-facing view of extended-block assignments (Belbin/АСТУР),
PRO-338 post-Ф4.1 follow-up. The assign action itself lives in
psychologist.py (only a psychologist/admin may assign) — this router is
the read-only counterpart the STUDENT's own UI polls to discover what's
been assigned to them, replacing the raw hand-delivered link Ф2.6/Ф3.6
originally shipped with."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.assessment import Assessment
from app.models.profile import Profile
from app.models.user import User
from app.schemas.extended_block import ExtendedBlockAssignmentResponse, ExtendedBlocksResponse
from app.services import extended_block_service

router = APIRouter(tags=["extended-blocks"])


@router.get("/{assessment_id}/extended-blocks", response_model=ExtendedBlocksResponse)
async def get_extended_blocks(
    assessment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExtendedBlocksResponse:
    """Same ownership check as belbin.py/astur.py's own submit endpoints —
    a student only ever sees their own assignments."""
    row = (
        await db.execute(
            select(Assessment.id, Profile.user_id)
            .join(Profile, Assessment.profile_id == Profile.id)
            .where(Assessment.id == assessment_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    if row.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    assignments = await extended_block_service.list_assignments(assessment_id, db)
    return ExtendedBlocksResponse(
        assignments=[ExtendedBlockAssignmentResponse(**a) for a in assignments]
    )
