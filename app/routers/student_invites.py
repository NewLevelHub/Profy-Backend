"""The student's side of the CRM invite link (ТЗ §4.4). Mounted at
`/api/v1/student-invites`; the link itself is made in the CRM deal."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.crm import StudentInviteAcceptIn
from app.services.crm import invites

router = APIRouter(tags=["student-invites"])


@router.post("/accept", status_code=status.HTTP_204_NO_CONTENT)
async def accept(
    body: StudentInviteAcceptIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    """The signed-in student opened the link: their account joins the deal."""
    await invites.accept_invite(db, user, body.token)
