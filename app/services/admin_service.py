import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult
from app.models.artifact import Artifact
from app.models.assessment import Assessment
from app.models.profile import Profile
from app.models.roadmap import Roadmap
from app.models.question import Question
from app.models.user import User
from app.models.user_response import UserResponse
from app.schemas.admin import (
    AdminAssessmentDetailResponse,
    AdminAssessmentSummary,
    AdminResponseItem,
    AdminUserDetailResponse,
    AdminUserListItem,
    AdminUserListResponse,
)
from app.schemas.artifact import ArtifactItem
from app.schemas.profile import ProfileResponse
from app.schemas.result import AnalysisResultResponse
from app.schemas.roadmap import RoadmapResponse
from app.services import riasec_service
from app.services.riasec_content import LIKERT_LABELS

RIASEC_ORDER = {letter: i for i, letter in enumerate(riasec_service.HOLLAND_ORDER)}


def _selected_answer_text(answer_value: int) -> str:
    if 1 <= answer_value <= len(LIKERT_LABELS):
        return LIKERT_LABELS[answer_value - 1]
    return f"Шкала {answer_value}/5"


async def list_users(
    db: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
) -> AdminUserListResponse:
    filters = []
    if search:
        filters.append(User.email.ilike(f"%{search.strip()}%"))

    total_result = await db.execute(select(func.count()).select_from(User).where(*filters))
    total = total_result.scalar_one()

    users_result = await db.execute(
        select(User)
        .where(*filters)
        .order_by(User.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    users = users_result.scalars().all()
    if not users:
        return AdminUserListResponse(items=[], total=total, page=page, limit=limit)

    user_ids = [user.id for user in users]
    profiles_result = await db.execute(select(Profile).where(Profile.user_id.in_(user_ids)))
    profiles_by_user = {profile.user_id: profile for profile in profiles_result.scalars().all()}

    profile_ids = [profile.id for profile in profiles_by_user.values()]
    assessments_by_profile: dict[uuid.UUID, list[Assessment]] = {pid: [] for pid in profile_ids}
    if profile_ids:
        assessments_result = await db.execute(
            select(Assessment)
            .where(Assessment.profile_id.in_(profile_ids))
            .order_by(Assessment.created_at.desc())
        )
        for assessment in assessments_result.scalars().all():
            assessments_by_profile[assessment.profile_id].append(assessment)

    items: list[AdminUserListItem] = []
    for user in users:
        profile = profiles_by_user.get(user.id)
        assessments = assessments_by_profile.get(profile.id, []) if profile else []
        latest = assessments[0] if assessments else None
        items.append(
            AdminUserListItem(
                id=user.id,
                email=user.email,
                is_verified=user.is_verified,
                is_active=user.is_active,
                is_admin=user.is_admin,
                created_at=user.created_at,
                has_profile=profile is not None,
                profile_name=profile.name if profile else None,
                assessments_count=len(assessments),
                latest_assessment_status=latest.status.value if latest else None,
            )
        )

    return AdminUserListResponse(items=items, total=total, page=page, limit=limit)


async def get_user_detail(db: AsyncSession, user_id: uuid.UUID) -> AdminUserDetailResponse | None:
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        return None

    profile_result = await db.execute(select(Profile).where(Profile.user_id == user.id))
    profile = profile_result.scalar_one_or_none()

    artifacts: list[ArtifactItem] = []
    assessments: list[AdminAssessmentSummary] = []

    if profile:
        artifacts_result = await db.execute(
            select(Artifact).where(Artifact.profile_id == profile.id).order_by(Artifact.created_at)
        )
        artifacts = [
            ArtifactItem(type=artifact.type, value=artifact.value)
            for artifact in artifacts_result.scalars().all()
        ]

        assessments_result = await db.execute(
            select(Assessment)
            .where(Assessment.profile_id == profile.id)
            .order_by(Assessment.created_at.desc())
        )
        assessment_rows = assessments_result.scalars().all()
        assessment_ids = [row.id for row in assessment_rows]

        result_ids: set[uuid.UUID] = set()
        roadmap_ids: set[uuid.UUID] = set()
        answered_by_assessment: dict[uuid.UUID, int] = {}
        if assessment_ids:
            results_result = await db.execute(
                select(AnalysisResult.assessment_id).where(
                    AnalysisResult.assessment_id.in_(assessment_ids)
                )
            )
            result_ids = {row[0] for row in results_result.all()}

            roadmaps_result = await db.execute(
                select(Roadmap.assessment_id).where(Roadmap.assessment_id.in_(assessment_ids))
            )
            roadmap_ids = {row[0] for row in roadmaps_result.all()}

            answered_result = await db.execute(
                select(UserResponse.assessment_id, func.count(UserResponse.id))
                .where(UserResponse.assessment_id.in_(assessment_ids))
                .group_by(UserResponse.assessment_id)
            )
            answered_by_assessment = dict(answered_result.all())

        total_questions_result = await db.execute(select(func.count(Question.id)))
        total_questions = total_questions_result.scalar_one()

        assessments = [
            AdminAssessmentSummary(
                id=assessment.id,
                goal=assessment.goal.value,
                status=assessment.status.value,
                answered_count=answered_by_assessment.get(assessment.id, 0),
                total_questions=total_questions,
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

    responses_result = await db.execute(
        select(UserResponse)
        .where(UserResponse.assessment_id == assessment.id)
        .order_by(UserResponse.created_at)
    )
    user_responses = responses_result.scalars().all()

    question_ids = [response.question_id for response in user_responses]
    questions_by_id: dict[uuid.UUID, Question] = {}
    if question_ids:
        questions_result = await db.execute(
            select(Question).where(Question.id.in_(question_ids))
        )
        questions_by_id = {question.id: question for question in questions_result.scalars().all()}

    responses: list[AdminResponseItem] = []
    for response in user_responses:
        question = questions_by_id.get(response.question_id)
        if question is None:
            responses.append(
                AdminResponseItem(
                    question_id=response.question_id,
                    riasec_type="?",
                    question_text="Вопрос удалён",
                    question_order=0,
                    answer_value=response.answer_value,
                    selected_answer_text=_selected_answer_text(response.answer_value),
                    created_at=response.created_at,
                )
            )
            continue

        responses.append(
            AdminResponseItem(
                question_id=response.question_id,
                riasec_type=question.riasec_type.value,
                question_text=question.text,
                question_order=question.order,
                answer_value=response.answer_value,
                selected_answer_text=_selected_answer_text(response.answer_value),
                created_at=response.created_at,
            )
        )

    responses.sort(
        key=lambda item: (
            RIASEC_ORDER.get(item.riasec_type, 99),
            item.question_order,
            item.created_at,
        )
    )

    analysis_result = None
    analysis_row = await db.execute(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment.id)
    )
    analysis = analysis_row.scalar_one_or_none()
    if analysis:
        analysis_result = AnalysisResultResponse.model_validate(analysis)

    roadmap_result = None
    roadmap_row = await db.execute(select(Roadmap).where(Roadmap.assessment_id == assessment.id))
    roadmap = roadmap_row.scalar_one_or_none()
    if roadmap:
        roadmap_result = RoadmapResponse.model_validate(roadmap)

    total_questions_result = await db.execute(select(func.count(Question.id)))
    total_questions = total_questions_result.scalar_one()

    return AdminAssessmentDetailResponse(
        id=assessment.id,
        user_id=user.id,
        user_email=user.email,
        profile_name=profile.name,
        goal=assessment.goal.value,
        status=assessment.status.value,
        answered_count=len(user_responses),
        total_questions=total_questions,
        created_at=assessment.created_at,
        completed_at=assessment.completed_at,
        responses=responses,
        analysis_result=analysis_result,
        roadmap=roadmap_result,
    )
