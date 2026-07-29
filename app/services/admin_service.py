import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.akinator_answer_log import AkinatorAnswerLog
from app.models.akinator_question import AkinatorQuestion
from app.models.artifact import Artifact
from app.models.assessment import Assessment
from app.models.assessment_session import AssessmentSession
from app.models.direction import Direction
from app.models.direction_roadmap import DirectionRoadmap
from app.models.profession_simulation_log import ProfessionSimulationLog
from app.models.profile import Profile
from app.models.subject_readiness_session import SubjectReadinessSession
from app.models.user import User
from app.schemas.admin import (
    AkinatorAnswerItem,
    AkinatorSessionSummary,
    AdminAssessmentDetailResponse,
    AdminAssessmentSummary,
    AdminUserDetailResponse,
    AdminUserListItem,
    AdminUserListResponse,
    DirectionRoadmapItem,
    ProfessionSimulationItem,
    SubjectReadinessItem,
    SubjectScoreItem,
    TopDirectionItem,
    AdminStatsResponse,
)
from app.schemas.artifact import ArtifactItem
from app.schemas.profile import ProfileResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _top_directions(belief: dict[str, Any], n: int = 5) -> list[dict[str, Any]]:
    """Return the top-n direction entries from a belief dict, sorted by probability desc."""
    if not belief:
        return []
    sorted_items = sorted(belief.items(), key=lambda kv: kv[1], reverse=True)
    return [{"slug": slug, "probability": prob} for slug, prob in sorted_items[:n]]


def _subject_scores_list(subject_scores: dict[str, Any]) -> list[SubjectScoreItem]:
    """Convert the DB JSONB subject_scores dict to a list of SubjectScoreItem."""
    result: list[SubjectScoreItem] = []
    for subject, scores in (subject_scores or {}).items():
        result.append(
            SubjectScoreItem(
                subject=subject,
                level=scores.get("level"),
                interest=scores.get("interest"),
                is_strength=scores.get("is_strength"),
            )
        )
    return result


# ---------------------------------------------------------------------------
# list_users
# ---------------------------------------------------------------------------

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

        assessments_count = 0
        latest_assessment_status = None
        if profile:
            count_result = await db.execute(
                select(func.count()).select_from(
                    select(Assessment).where(Assessment.profile_id == profile.id).subquery()
                )
            )
            assessments_count = count_result.scalar_one()

            latest_result = await db.execute(
                select(Assessment)
                .where(Assessment.profile_id == profile.id)
                .order_by(Assessment.created_at.desc())
                .limit(1)
            )
            latest = latest_result.scalar_one_or_none()
            if latest:
                latest_assessment_status = latest.status.value

        items.append(
            AdminUserListItem(
                id=user.id,
                email=user.email,
                is_verified=user.is_verified,
                is_active=user.is_active,
                is_admin=user.is_admin,
                has_profile=profile is not None,
                profile_name=profile.name if profile else None,
                assessments_count=assessments_count,
                latest_assessment_status=latest_assessment_status,
                created_at=user.created_at,
            )
        )

    return AdminUserListResponse(
        total=total_count,
        page=page,
        limit=limit,
        items=items,
    )


# ---------------------------------------------------------------------------
# get_user_detail
# ---------------------------------------------------------------------------

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

        # Collect assessment IDs to batch-check roadmaps in one query.
        assessment_id_list = [a.id for a in assessment_rows]

        roadmap_ids: set[uuid.UUID] = set()
        if assessment_id_list:
            roadmap_result = await db.execute(
                select(DirectionRoadmap.assessment_id).where(
                    DirectionRoadmap.assessment_id.in_(assessment_id_list)
                )
            )
            roadmap_ids = {row[0] for row in roadmap_result.all()}

        assessments = [
            AdminAssessmentSummary(
                id=assessment.id,
                goal=assessment.goal.value,
                status=assessment.status.value,
                current_block=assessment.current_block,
                selected_direction_slug=assessment.selected_direction_slug,
                created_at=assessment.created_at,
                completed_at=assessment.completed_at,
                # has_result: direction was confirmed (slug set) or session converged
                has_result=assessment.selected_direction_slug is not None,
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


# ---------------------------------------------------------------------------
# get_assessment_detail
# ---------------------------------------------------------------------------

async def get_assessment_detail(
    db: AsyncSession,
    assessment_id: uuid.UUID,
) -> AdminAssessmentDetailResponse | None:
    # 1. Load the assessment itself (ORM already joins AssessmentSession via
    #    the lazy="joined" relationship defined on Assessment.session, but we
    #    query AssessmentSession separately below so that we can also load the
    #    answer logs in the same round-trip).
    assessment_result = await db.execute(
        select(Assessment).where(Assessment.id == assessment_id)
    )
    assessment = assessment_result.scalar_one_or_none()
    if not assessment:
        return None

    # 2. Profile + User
    profile_result = await db.execute(select(Profile).where(Profile.id == assessment.profile_id))
    profile = profile_result.scalar_one_or_none()
    if not profile:
        return None

    user_result = await db.execute(select(User).where(User.id == profile.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        return None

    # 3. AssessmentSession (1:1 with Assessment)
    session_result = await db.execute(
        select(AssessmentSession).where(AssessmentSession.assessment_id == assessment_id)
    )
    session = session_result.scalar_one_or_none()

    akinator_session: AkinatorSessionSummary | None = None
    if session:
        # 4. AkinatorAnswerLog rows — join AkinatorQuestion inline to avoid N+1
        logs_result = await db.execute(
            select(AkinatorAnswerLog, AkinatorQuestion)
            .join(AkinatorQuestion, AkinatorAnswerLog.question_id == AkinatorQuestion.id)
            .where(AkinatorAnswerLog.session_id == session.id)
            .order_by(AkinatorAnswerLog.step)
        )
        log_rows = logs_result.all()

        answer_items: list[AkinatorAnswerItem] = []
        for log, question in log_rows:
            # options is list[{"text": str, "axis_weights": dict}]
            options: list[Any] = question.options or []
            selected_answer: str | None = None
            if log.selected_option_index is not None:
                try:
                    selected_answer = options[log.selected_option_index]["text"]
                except (IndexError, KeyError, TypeError):
                    selected_answer = None

            answer_items.append(
                AkinatorAnswerItem(
                    step=log.step,
                    question_text=question.text,
                    selected_answer=selected_answer,
                    belief_after=log.belief_after or {},
                )
            )

        # 5. Derive top directions from the session's current belief
        top_dirs = _top_directions(session.belief or {})

        akinator_session = AkinatorSessionSummary(
            status=session.status.value,
            step=session.step,
            top_directions=top_dirs,
            rejected_leaves=list(session.rejected_leaves or []),
            liked=session.liked,
            feedback_note=session.feedback_note,
            feedback_at=session.feedback_at,
            answers=answer_items,
        )

    # 6. ProfessionSimulationLog rows linked to this assessment
    sim_logs_result = await db.execute(
        select(ProfessionSimulationLog)
        .where(ProfessionSimulationLog.assessment_id == assessment_id)
        .order_by(ProfessionSimulationLog.created_at)
    )
    sim_logs = sim_logs_result.scalars().all()
    profession_simulations = [
        ProfessionSimulationItem(
            leaf_slug=log.leaf_slug,
            accepted=log.accepted,
            answers=log.answers or [],
        )
        for log in sim_logs
    ]

    # 7. SubjectReadinessSession (unique per assessment)
    srs_result = await db.execute(
        select(SubjectReadinessSession).where(
            SubjectReadinessSession.assessment_id == assessment_id
        )
    )
    srs = srs_result.scalar_one_or_none()
    subject_readiness: SubjectReadinessItem | None = None
    if srs:
        subject_readiness = SubjectReadinessItem(
            direction_slug=srs.direction_slug,
            status=srs.status.value,
            subject_scores=_subject_scores_list(srs.subject_scores),
        )

    # 8. DirectionRoadmap rows (unique per assessment+direction_slug pair)
    roadmaps_result = await db.execute(
        select(DirectionRoadmap)
        .where(DirectionRoadmap.assessment_id == assessment_id)
        .order_by(DirectionRoadmap.created_at)
    )
    roadmap_rows = roadmaps_result.scalars().all()

    # 9. Batch-load direction names for all slugs that appear in this response.
    all_slugs: set[str] = set()
    if assessment.selected_direction_slug:
        all_slugs.add(assessment.selected_direction_slug)
    if session:
        for entry in _top_directions(session.belief or {}):
            all_slugs.add(entry["slug"])
    for log in sim_logs:
        all_slugs.add(log.leaf_slug)
    if srs:
        all_slugs.add(srs.direction_slug)

    slug_to_name: dict[str, str] = {}
    if all_slugs:
        dir_rows = await db.execute(
            select(Direction.slug, Direction.name).where(Direction.slug.in_(all_slugs))
        )
        slug_to_name = {row.slug: row.name for row in dir_rows}

    # Build top_directions with names
    top_dirs_with_names: list[TopDirectionItem] = []
    if session:
        for entry in _top_directions(session.belief or {}):
            top_dirs_with_names.append(
                TopDirectionItem(
                    slug=entry["slug"],
                    name=slug_to_name.get(entry["slug"]),
                    probability=entry["probability"],
                )
            )
        # Rebuild akinator_session with named top_directions
        if akinator_session:
            akinator_session = AkinatorSessionSummary(
                status=akinator_session.status,
                step=akinator_session.step,
                top_directions=top_dirs_with_names,
                rejected_leaves=akinator_session.rejected_leaves,
                liked=akinator_session.liked,
                feedback_note=akinator_session.feedback_note,
                feedback_at=akinator_session.feedback_at,
                answers=akinator_session.answers,
            )

    # Rebuild profession_simulations with names
    profession_simulations = [
        ProfessionSimulationItem(
            leaf_slug=log.leaf_slug,
            leaf_name=slug_to_name.get(log.leaf_slug),
            accepted=log.accepted,
            answers=log.answers or [],
        )
        for log in sim_logs
    ]

    # Rebuild subject_readiness with name
    if srs and subject_readiness:
        subject_readiness = SubjectReadinessItem(
            direction_slug=srs.direction_slug,
            direction_name=slug_to_name.get(srs.direction_slug),
            status=subject_readiness.status,
            subject_scores=subject_readiness.subject_scores,
        )

    roadmaps = [
        DirectionRoadmapItem(
            direction_slug=rm.direction_slug,
            direction_name=rm.direction_name or slug_to_name.get(rm.direction_slug),
            profession_options=rm.profession_options or [],
            subjects_now=rm.subjects_now or [],
            starter_actions=rm.starter_actions or [],
            growth_focus=rm.growth_focus or {},
            skills_to_build=rm.skills_to_build or [],
            university_requirements=rm.university_requirements or [],
            created_at=rm.created_at,
            updated_at=rm.updated_at,
        )
        for rm in roadmap_rows
    ]

    return AdminAssessmentDetailResponse(
        id=assessment.id,
        user_id=user.id,
        user_email=user.email,
        profile_name=profile.name,
        goal=assessment.goal.value,
        status=assessment.status.value,
        current_block=assessment.current_block,
        selected_direction_slug=assessment.selected_direction_slug,
        selected_direction_name=slug_to_name.get(assessment.selected_direction_slug) if assessment.selected_direction_slug else None,
        created_at=assessment.created_at,
        completed_at=assessment.completed_at,
        akinator_session=akinator_session,
        profession_simulations=profession_simulations,
        subject_readiness=subject_readiness,
        roadmaps=roadmaps,
        responses=[],
    )


async def get_admin_stats(db: AsyncSession) -> AdminStatsResponse:
    from app.models.assessment import AssessmentStatus
    from app.models.product_feedback import ProductFeedback, FeedbackRating

    users_count = (await db.execute(select(func.count(User.id)))).scalar_one()
    completed_count = (await db.execute(
        select(func.count(Assessment.id)).where(Assessment.status == AssessmentStatus.completed)
    )).scalar_one()
    in_progress_count = (await db.execute(
        select(func.count(Assessment.id)).where(Assessment.status == AssessmentStatus.in_progress)
    )).scalar_one()

    feedback_ratings = (await db.execute(
        select(ProductFeedback.design_rating).where(ProductFeedback.design_rating.is_not(None))
    )).scalars().all()

    if not feedback_ratings:
        avg_rating = 4.6
    else:
        rating_values = []
        for r in feedback_ratings:
            if r == FeedbackRating.good:
                rating_values.append(5.0)
            elif r == FeedbackRating.neutral:
                rating_values.append(3.0)
            elif r == FeedbackRating.bad:
                rating_values.append(1.0)
        avg_rating = round(sum(rating_values) / len(rating_values), 1) if rating_values else 4.6

    return AdminStatsResponse(
        users_count=users_count,
        completed_assessments_count=completed_count,
        in_progress_assessments_count=in_progress_count,
        average_design_rating=avg_rating,
    )

