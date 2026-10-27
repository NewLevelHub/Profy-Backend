"""Staff email invitations (PRO-460). Contract:
docs/frontend-admin-invitations-api-contract.md.

Open to the platform admin and to the business owner, who runs the CRM
staff (ТЗ CRM Profile v4.1 §2 has no separate administrator role; PRO-497).
The owner sees and manages only specialists and the CRM team
(`invitation_service.OWNER_INVITABLE_ROLES`); the CRM «Сотрудники» page is
built on these endpoints."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.invitation import InvitationStatus
from app.models.user import User, UserRole
from app.schemas.invitation import (
    AdminInvitationCreate,
    AdminInvitationItem,
    AdminInvitationLink,
    AdminInvitationListResponse,
    AdminInvitationSent,
)
from app.services import invitation_service

router = APIRouter(tags=["admin-invitations"])

_require_inviter = require_role(UserRole.admin, UserRole.owner)


@router.post("", response_model=AdminInvitationSent, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    body: AdminInvitationCreate,
    admin: User = Depends(_require_inviter),
    db: AsyncSession = Depends(get_db),
) -> AdminInvitationSent:
    return await invitation_service.create_invitation(db, body, inviter=admin)


@router.get("", response_model=AdminInvitationListResponse)
async def list_invitations(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: InvitationStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    user: User = Depends(_require_inviter),
    db: AsyncSession = Depends(get_db),
) -> AdminInvitationListResponse:
    return await invitation_service.list_invitations(
        db, page=page, limit=limit, status_filter=status_filter, search=search,
        roles=invitation_service.invitable_roles(user),
    )


@router.get("/{invitation_id}/link", response_model=AdminInvitationLink)
async def invitation_link(
    invitation_id: uuid.UUID,
    user: User = Depends(_require_inviter),
    db: AsyncSession = Depends(get_db),
) -> AdminInvitationLink:
    return await invitation_service.invitation_link(db, invitation_id, invitation_service.invitable_roles(user))


@router.post("/{invitation_id}/resend", response_model=AdminInvitationSent)
async def resend_invitation(
    invitation_id: uuid.UUID,
    user: User = Depends(_require_inviter),
    db: AsyncSession = Depends(get_db),
) -> AdminInvitationSent:
    return await invitation_service.resend_invitation(db, invitation_id, invitation_service.invitable_roles(user))


@router.delete("/{invitation_id}", response_model=AdminInvitationItem)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    user: User = Depends(_require_inviter),
    db: AsyncSession = Depends(get_db),
) -> AdminInvitationItem:
    return await invitation_service.revoke_invitation(db, invitation_id, invitation_service.invitable_roles(user))
