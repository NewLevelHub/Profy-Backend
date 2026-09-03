from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.i18n import guess_locale_from_language_field
from app.models.artifact import Artifact
from app.models.certificate import Certificate
from app.models.profile import Profile
from app.models.user import User
from app.schemas.artifact import ArtifactItem
from app.schemas.certificate import CertificateItem
from app.schemas.profile import (
    ProfileCreateRequest,
    ProfileResponse,
    ProfileUpdateRequest,
)
from app.services import artifact_service, certificate_service, profile_service

router = APIRouter(tags=["profile"])


def _to_response(
    profile: Profile, artifacts: list[Artifact], certificates: list[Certificate]
) -> ProfileResponse:
    return ProfileResponse.model_validate(profile).model_copy(
        update={
            "artifacts": [ArtifactItem(type=a.type, value=a.value) for a in artifacts],
            "certificates": [CertificateItem(type=c.type, score=c.score) for c in certificates],
        }
    )


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    data: ProfileCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Create the caller's Profile, optionally saving their artifact and/or
    certificate selections in the same request/transaction (`data.artifacts`,
    `data.certificates`). `gpa_value`/`gpa_scale` are plain Profile columns,
    written by `profile_service.create_profile` itself.

    All writes commit together: if artifact/certificate persistence fails
    after the profile insert has been flushed, nothing is committed and the
    whole request rolls back — no half-created profile. Clients that omit
    `artifacts`/`certificates` (or still call the old two-step flow) are
    unaffected: this is purely additive to the existing contract.
    """
    try:
        profile = await profile_service.create_profile(current_user.id, data, db, commit=False)

        # Pre-fill the UI locale from the "language of instruction" field at
        # profile creation. Gated ONLY on `locale_explicit` (contract §6): while
        # the user has never picked a locale via the switcher, the language
        # field is the authoritative implicit signal and always wins — including
        # over an `Accept-Language`-seeded "kk" when the language of instruction
        # is Russian. The heuristic yields "kk" or "ru", so this can move the
        # value either way. Any explicit switcher choice disables this for good.
        if not current_user.locale_explicit:
            current_user.locale = guess_locale_from_language_field(data.language)

        saved_artifacts: list[Artifact] = []
        if data.artifacts is not None:
            saved_artifacts = await artifact_service.save_artifacts(
                profile.id, data.artifacts, db, commit=False
            )

        saved_certificates: list[Certificate] = []
        if data.certificates is not None:
            saved_certificates = await certificate_service.save_certificates(
                profile.id, data.certificates, db, commit=False
            )

        await db.commit()
        await db.refresh(profile)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return _to_response(profile, saved_artifacts, saved_certificates)


@router.get("", response_model=ProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    profile = await profile_service.get_profile(current_user.id, db)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    artifacts = await artifact_service.get_artifacts(profile.id, db)
    certificates = await certificate_service.get_certificates(profile.id, db)
    return _to_response(profile, artifacts, certificates)


@router.put("", response_model=ProfileResponse)
async def update_profile(
    data: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Update the caller's Profile, optionally replacing their artifacts
    and/or certificates in the same transaction (`data.artifacts`,
    `data.certificates`) — same combined-write contract as POST. Omitting
    either leaves it untouched; the response still echoes the current set
    either way.
    """
    try:
        profile, artifacts, certificates = await profile_service.update_profile(
            current_user.id, data, db
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return _to_response(profile, artifacts, certificates)
