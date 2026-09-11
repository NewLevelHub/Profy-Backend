from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_student_user
from app.models.user import User
from app.schemas.certificate import CertificateItem, CertificatesBulkRequest, CertificatesResponse
from app.services import certificate_service
from app.services.profile_service import get_profile

router = APIRouter(tags=["certificates"])


async def _require_profile_id(current_user: User, db: AsyncSession) -> object:
    profile = await get_profile(current_user.id, db)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile.id


@router.post("", response_model=CertificatesResponse)
async def save_certificates(
    data: CertificatesBulkRequest,
    current_user: User = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_db),
) -> CertificatesResponse:
    profile_id = await _require_profile_id(current_user, db)
    certificates = await certificate_service.save_certificates(profile_id, data.items, db)
    return CertificatesResponse(
        items=[CertificateItem(type=c.type, score=c.score) for c in certificates]
    )


@router.get("", response_model=CertificatesResponse)
async def get_certificates(
    current_user: User = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_db),
) -> CertificatesResponse:
    profile_id = await _require_profile_id(current_user, db)
    certificates = await certificate_service.get_certificates(profile_id, db)
    return CertificatesResponse(
        items=[CertificateItem(type=c.type, score=c.score) for c in certificates]
    )
