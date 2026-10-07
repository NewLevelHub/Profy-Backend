"""Admin: staff email invitations (PRO-460). Contract:
docs/frontend-admin-invitations-api-contract.md."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_admin_user
from app.models.invitation import InvitationStatus
from app.models.user import User
from app.schemas.invitation import (
    AdminInvitationCreate,
    AdminInvitationItem,
    AdminInvitationListResponse,
    AdminInvitationSent,
)
from app.services import invitation_service

router = APIRouter(tags=["admin-invitations"])


@router.post("", response_model=AdminInvitationSent, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    body: AdminInvitationCreate,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> AdminInvitationSent:
    return await invitation_service.create_invitation(db, body, inviter=admin)


@router.get("", response_model=AdminInvitationListResponse)
async def list_invitations(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: InvitationStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> AdminInvitationListResponse:
    return await invitation_service.list_invitations(
        db, page=page, limit=limit, status_filter=status_filter, search=search
    )


@router.post("/{invitation_id}/resend", response_model=AdminInvitationSent)
async def resend_invitation(
    invitation_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> AdminInvitationSent:
    return await invitation_service.resend_invitation(db, invitation_id)


@router.delete("/{invitation_id}", response_model=AdminInvitationItem)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> AdminInvitationItem:
    return await invitation_service.revoke_invitation(db, invitation_id)
