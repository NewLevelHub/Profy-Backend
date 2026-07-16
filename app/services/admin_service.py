import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact import Artifact
from app.models.assessment import Assessment
from app.models.profile import Profile
from app.models.user import User
from app.schemas.admin import (
    AdminAssessmentDetailResponse,
    AdminAssessmentSummary,
    AdminUserDetailResponse,
    AdminUserListItem,
    AdminUserListResponse,
)
from app.schemas.artifact import ArtifactItem
from app.schemas.profile import ProfileResponse


async def list_users(
    db: AsyncSession,
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
) -> AdminUserListResponse:
    offset = (page - 1) * limit

    query = select(User)
    if search:
        search_filter = f"%{search}%"
        query = query.join(Profile, User.id == Profile.user_id, isouter=True).where(
            User.email.ilike(search_filter) | Profile.name.ilike(search_filter)
        )

    count_query = select(func.count()).select_from(query.subquery())
    total_count = (await db.execute(count_query)).scalar_one()

    query = query.order_by(User.created_at.desc()).offset(offset).limit(limit)
    users = (await db.execute(query)).scalars().all()

    items: list[AdminUserListItem] = []
    for user in users:
        profile_result = await db.execute(
            select(Profile).where(Profile.user_id == user.id)
        )
        profile = profile_result.scalar_one_or_none()

        items.append(
            AdminUserListItem(
                id=user.id,
                email=user.email,
                is_verified=user.is_verified,
                is_active=user.is_active,
                is_admin=user.is_admin,
                profile_name=profile.name if profile else None,
                created_at=user.created_at,
            )
        )

    return AdminUserListResponse(
        total=total_count,
        page=page,
        limit=limit,
        items=items,
    )


async def get_user_detail(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> AdminUserDetailResponse | None:
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        return None

    profile_result = await db.execute(select(Profile).where(Profile.user_id == user_id))
    profile = profile_result.scalar_one_or_none()

    artifacts: list[ArtifactItem] = []
    assessments: list[AdminAssessmentSummary] = []

    if profile:
        artifacts_result = await db.execute(
            select(Artifact).where(Artifact.profile_id == profile.id)
        )
        artifacts = [
            ArtifactItem(id=artifact.id, type=artifact.type, value=artifact.value)
            for artifact in artifacts_result.scalars().all()
        ]

        assessments_result = await db.execute(
            select(Assessment)
            .where(Assessment.profile_id == profile.id)
            .order_by(Assessment.created_at.desc())
        )
        assessment_rows = assessments_result.scalars().all()

        result_ids: set[uuid.UUID] = set()
        roadmap_ids: set[uuid.UUID] = set()

        assessments = [
            AdminAssessmentSummary(
                id=assessment.id,
                goal=assessment.goal.value,
                status=assessment.status.value,
                current_block=assessment.current_block,
                created_at=assessment.created_at,
                completed_at=assessment.completed_at,
                has_result=assessment.id in result_ids,
                has_roadmap=assessment.id in roadmap_ids,
            )
            for assessment in assessment_rows
        ]

    return AdminUserDetailResponse(
        id=user.id,
        email=user.email,
        is_verified=user.is_verified,
        is_active=user.is_active,
        is_admin=user.is_admin,
        created_at=user.created_at,
        profile=ProfileResponse.model_validate(profile) if profile else None,
        artifacts=artifacts,
        assessments=assessments,
    )


async def get_assessment_detail(
    db: AsyncSession,
    assessment_id: uuid.UUID,
) -> AdminAssessmentDetailResponse | None:
    assessment_result = await db.execute(
        select(Assessment).where(Assessment.id == assessment_id)
    )
    assessment = assessment_result.scalar_one_or_none()
    if not assessment:
        return None

    profile_result = await db.execute(select(Profile).where(Profile.id == assessment.profile_id))
    profile = profile_result.scalar_one_or_none()
    if not profile:
        return None

    user_result = await db.execute(select(User).where(User.id == profile.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        return None

    return AdminAssessmentDetailResponse(
        id=assessment.id,
        user_id=user.id,
        user_email=user.email,
        profile_name=profile.name,
        goal=assessment.goal.value,
        status=assessment.status.value,
        current_block=assessment.current_block,
        created_at=assessment.created_at,
        completed_at=assessment.completed_at,
        responses=[],
        analysis_result=None,
        roadmap=None,
    )
