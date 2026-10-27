"""«Сотрудники» in the CRM: the owner sees the business staff — the owners,
the specialists and the CRM team. New people come by email invitation
(`/admin/invitations`, limited for the owner to
`invitation_service.OWNER_INVITABLE_ROLES`)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.schemas import crm as schemas
from app.services.invitation_service import OWNER_INVITABLE_ROLES

STAFF_ROLES = (UserRole.owner, *OWNER_INVITABLE_ROLES)


async def members(db: AsyncSession) -> list[schemas.StaffMember]:
    rows = await db.execute(
        select(User).where(User.role.in_(STAFF_ROLES)).order_by(User.is_active.desc(), User.full_name, User.email)
    )
    return [
        schemas.StaffMember(
            id=u.id, email=u.email, full_name=u.full_name, role=u.role.value, is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in rows.scalars()
    ]
