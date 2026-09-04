import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import DEFAULT_LOCALE
from app.models.analysis_result import AnalysisResult
from app.models.artifact import Artifact
from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.motivation import MotivationResponse
from app.models.product_feedback import ProductFeedback
from app.models.profile import AgeGroup, Profile
from app.models.roadmap import Roadmap
from app.models.question import Question, QuestionInstrument
from app.models.user import User
from app.models.user_response import UserResponse
from app.schemas.admin import (
    AdminAssessmentDetailResponse,
    AdminAssessmentSummary,
    AdminFeedbackListItem,
    AdminFeedbackListResponse,
    AdminFeedbackStatsResponse,
    AdminMotivationResponseItem,
    AdminResponseItem,
    AdminUserDetailResponse,
    AdminUserListItem,
    AdminUserListResponse,
    FeedbackBreakdownItem,
)
from app.schemas.artifact import ArtifactItem
from app.schemas.profile import ProfileResponse
from app.schemas.admin_result import AdminAnalysisResultResponse
from app.schemas.roadmap import RoadmapResponse
from app.services import bigfive_content, motivation_service
from app.services.age_tiers import visible_tiers
from app.services.goal_overlay_service import _get_effective_goal_and_scenario
from app.services.riasec_content import likert_labels as riasec_likert_labels

# GET /admin/users/export has no page/limit — unlike list_users, it always
# fetches every matching row (plus their profiles/assessments/analysis
# results) into memory before building the CSV. This cap turns an unbounded
# query + full in-memory result set into a clean, actionable error instead
# of a slow request that risks a timeout or holds a DB connection for the
# whole build, as the dataset grows.
EXPORT_MAX_ROWS = 5000


class ExportTooLargeError(Exception):
    """Raised by export_users() when the filtered result set exceeds
    EXPORT_MAX_ROWS — narrow the filters (search/age_group/status/goal)
    instead of exporting everyone at once."""


def _selected_answer_text(answer_value: int, instrument: QuestionInstrument | None = None) -> str:
    labels = bigfive_content.likert_labels() if instrument == QuestionInstrument.big_five else riasec_likert_labels()
    if 1 <= answer_value <= len(labels):
        return labels[answer_value - 1]
    return f"Шкала {answer_value}/5"


def _build_user_filters(
    *,
    search: str | None,
    age_group: AgeGroup | None,
    status: AssessmentStatus | None,
    goal: AssessmentGoal | None,
) -> tuple[list, bool]:
    """Filter clauses for the admin users list/export query, plus whether an
    Assessment join is needed. `status`/`goal` match "this user has AT LEAST
    ONE assessment matching", not necessarily their latest one — the already-
    exposed `latest_assessment_status`/`latest_assessment_goal` columns keep
    reflecting the true latest, independent of this filter. A user can have
    multiple assessments matching, so joining Assessment needs `.distinct()`
    on the caller's side; `age_group` only needs the (always-present, 1:1)
    Profile join, no distinct."""
    filters = []
    if search:
        filters.append(User.email.ilike(f"%{search.strip()}%"))
    if age_group is not None:
        filters.append(Profile.age_group == age_group)
    needs_distinct = status is not None or goal is not None
    if status is not None:
        filters.append(Assessment.status == status)
    if goal is not None:
        filters.append(Assessment.goal == goal)
    return filters, needs_distinct


def _user_base_query(*, needs_distinct: bool):
    query = select(User).outerjoin(Profile, Profile.user_id == User.id)
    if needs_distinct:
        query = query.outerjoin(Assessment, Assessment.profile_id == Profile.id)
    return query


async def list_users(
    db: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    age_group: AgeGroup | None = None,
    status: AssessmentStatus | None = None,
    goal: AssessmentGoal | None = None,
) -> AdminUserListResponse:
    filters, needs_distinct = _build_user_filters(
        search=search, age_group=age_group, status=status, goal=goal
    )

    count_query = _user_base_query(needs_distinct=needs_distinct).with_only_columns(User.id).where(*filters)
    if needs_distinct:
        count_query = count_query.distinct()
    total_result = await db.execute(select(func.count()).select_from(count_query.subquery()))
    total = total_result.scalar_one()

    query = _user_base_query(needs_distinct=needs_distinct).where(*filters).order_by(User.created_at.desc())
    if needs_distinct:
        query = query.distinct()
    query = query.offset((page - 1) * limit).limit(limit)
    users_result = await db.execute(query)
    users = users_result.scalars().all()

    items = await _build_user_list_items(db, list(users))
    return AdminUserListResponse(items=items, total=total, page=page, limit=limit)


async def export_users(
    db: AsyncSession,
    *,
    search: str | None = None,
    age_group: AgeGroup | None = None,
    status: AssessmentStatus | None = None,
    goal: AssessmentGoal | None = None,
) -> list[AdminUserListItem]:
    """Same filters as `list_users`, no pagination — for CSV export. Raises
    ExportTooLargeError instead of running an unbounded query if the
    filtered result set is bigger than EXPORT_MAX_ROWS."""
    filters, needs_distinct = _build_user_filters(
        search=search, age_group=age_group, status=status, goal=goal
    )

    count_query = _user_base_query(needs_distinct=needs_distinct).with_only_columns(User.id).where(*filters)
    if needs_distinct:
        count_query = count_query.distinct()
    total_result = await db.execute(select(func.count()).select_from(count_query.subquery()))
    total = total_result.scalar_one()
    if total > EXPORT_MAX_ROWS:
        raise ExportTooLargeError(
            f"Export matches {total} users, exceeding the {EXPORT_MAX_ROWS}-row limit — "
            "narrow the search/age_group/status/goal filters first."
        )

    query = _user_base_query(needs_distinct=needs_distinct).where(*filters).order_by(User.created_at.desc())
    if needs_distinct:
        query = query.distinct()
    users_result = await db.execute(query)
    users = users_result.scalars().all()
    return await _build_user_list_items(db, list(users))


async def _build_user_list_items(db: AsyncSession, users: list[User]) -> list[AdminUserListItem]:
    if not users:
        return []

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

    # Admin-only raw percentages (TZ_Profi.md §18.3) for the results columns
    # in the users table — sourced from each profile's latest COMPLETED
    # assessment (assessments are already sorted desc per profile above, so
    # the first `completed` one found is the latest). One batch fetch of
    # AnalysisResult keyed by assessment_id, same pattern as the assessments
    # batch fetch above.
    completed_assessment_ids = [
        assessment.id
        for assessments in assessments_by_profile.values()
        for assessment in assessments
        if assessment.status == AssessmentStatus.completed
    ]
    analysis_by_assessment: dict[uuid.UUID, AnalysisResult] = {}
    if completed_assessment_ids:
        analysis_result = await db.execute(
            select(AnalysisResult).where(AnalysisResult.assessment_id.in_(completed_assessment_ids))
        )
        for analysis in analysis_result.scalars().all():
            # KZ-405: one row per locale — admin is ru-only, prefer the ru row,
            # but still show a kk-only user's row if that's all there is.
            prev = analysis_by_assessment.get(analysis.assessment_id)
            if prev is None or analysis.locale == DEFAULT_LOCALE:
                analysis_by_assessment[analysis.assessment_id] = analysis

    items: list[AdminUserListItem] = []
    for user in users:
        profile = profiles_by_user.get(user.id)
        assessments = assessments_by_profile.get(profile.id, []) if profile else []
        latest = assessments[0] if assessments else None

        latest_completed = next((a for a in assessments if a.status == AssessmentStatus.completed), None)
        latest_analysis = analysis_by_assessment.get(latest_completed.id) if latest_completed else None
        # RIASEC is only meaningful for middle/senior — junior's instrument
        # is MI, deliberately left blank here rather than mixing shapes.
        riasec = (
            dict(latest_analysis.profile)
            if latest_analysis and profile and profile.age_group != AgeGroup.junior
            else None
        )
        big_five = dict(latest_analysis.big_five) if latest_analysis else None

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
                age_group=profile.age_group.value if profile else None,
                assessments_count=len(assessments),
                latest_assessment_status=latest.status.value if latest else None,
                latest_assessment_goal=latest.goal.value if latest else None,
                riasec=riasec,
                big_five=big_five,
            )
        )

    return items


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

        total_questions_result = await db.execute(
            select(func.count(Question.id)).where(
                Question.age_tier.in_(visible_tiers(profile.age_group)),
                # ru-only denominator (admin is ru-only; KZ-301 — never
                # double-count once kk question rows exist).
                Question.locale == DEFAULT_LOCALE,
            )
        )
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
                    instrument="?",
                    category="?",
                    question_text="Вопрос удалён",
                    question_order=0,
                    answer_value=response.answer_value,
                    selected_answer_text=_selected_answer_text(response.answer_value),
                    created_at=response.created_at,
                )
            )
            continue

        # riasec_type/bigfive_domain/mi_category are all nullable columns
        # (only the one matching `instrument` is normally populated) — since
        # admin PATCH /admin/questions/{id} can null any of them out
        # (app/services/admin_content_service.py::update_question), fall
        # back to "?" instead of crashing on a None here, same convention
        # as the "question deleted" branch above.
        if question.instrument == QuestionInstrument.riasec:
            category = question.riasec_type.value if question.riasec_type else "?"
        elif question.instrument == QuestionInstrument.big_five:
            category = question.bigfive_domain.value if question.bigfive_domain else "?"
        else:
            category = question.mi_category.value if question.mi_category else "?"
        responses.append(
            AdminResponseItem(
                question_id=response.question_id,
                instrument=question.instrument.value,
                category=category,
                question_text=question.text,
                question_order=question.order,
                answer_value=response.answer_value,
                selected_answer_text=_selected_answer_text(response.answer_value, question.instrument),
                created_at=response.created_at,
            )
        )

    # `order` already reflects test administration sequence (RIASEC block,
    # then Big Five block — see bigfive_question_bank.py's order offset).
    responses.sort(key=lambda item: item.question_order)

    motivation_rows_result = await db.execute(
        select(MotivationResponse).where(MotivationResponse.assessment_id == assessment.id)
    )
    motivation_rows = motivation_rows_result.scalars().all()

    motivation_responses: list[AdminMotivationResponseItem] = []
    if motivation_rows:
        triplets = await motivation_service.triplets(db)
        for row in motivation_rows:
            statements = triplets.get(row.triplet_index, [])
            by_id = {s.id: s for s in statements}
            most = by_id.get(row.most_statement_id)
            least = by_id.get(row.least_statement_id)
            neutral = next(
                (s for s in statements if s.id not in (row.most_statement_id, row.least_statement_id)),
                None,
            )
            motivation_responses.append(
                AdminMotivationResponseItem(
                    triplet_index=row.triplet_index,
                    picked_most_text=most.text if most else "?",
                    picked_most_category=most.category.value if most else "?",
                    picked_least_text=least.text if least else "?",
                    picked_least_category=least.category.value if least else "?",
                    not_picked_text=neutral.text if neutral else "?",
                    not_picked_category=neutral.category.value if neutral else "?",
                    created_at=row.created_at,
                )
            )
        motivation_responses.sort(key=lambda item: item.triplet_index)

    analysis_result = None
    analysis_row = await db.execute(
        select(AnalysisResult)
        .where(AnalysisResult.assessment_id == assessment.id)
        .order_by((AnalysisResult.locale == DEFAULT_LOCALE).desc())  # KZ-405: prefer ru row
        .limit(1)
    )
    analysis = analysis_row.scalar_one_or_none()
    if analysis:
        analysis_result = AdminAnalysisResultResponse.model_validate(analysis)

    roadmap_result = None
    roadmap_row = await db.execute(select(Roadmap).where(Roadmap.assessment_id == assessment.id))
    roadmap = roadmap_row.scalar_one_or_none()
    if roadmap:
        roadmap_result = RoadmapResponse.model_validate(roadmap)

    total_questions_result = await db.execute(
        select(func.count(Question.id)).where(
            Question.age_tier.in_(visible_tiers(profile.age_group)),
            # ru-only denominator (admin is ru-only; KZ-301 — never double-count
            # once kk question rows exist).
            Question.locale == DEFAULT_LOCALE,
        )
    )
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
        motivation_responses=motivation_responses,
        analysis_result=analysis_result,
        roadmap=roadmap_result,
    )


async def _enrich_feedback_rows(
    db: AsyncSession, feedback_rows: list[ProductFeedback]
) -> list[AdminFeedbackListItem]:
    """Shared join/enrichment for both `list_feedback` (one page) and
    `get_feedback_stats` (all rows) — attaches user + assessment context
    (age_group, effective scenario, top matched direction) to each raw
    ProductFeedback row. `scenario` reuses goal_overlay_service's own
    age_group×goal matrix rather than re-deriving it, so it always agrees
    with what the student's actual results page showed them."""
    if not feedback_rows:
        return []

    user_ids = {f.user_id for f in feedback_rows}
    users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
    users_by_id = {u.id: u for u in users_result.scalars().all()}

    assessment_ids = [f.assessment_id for f in feedback_rows if f.assessment_id]
    assessments_by_id: dict[uuid.UUID, Assessment] = {}
    profiles_by_id: dict[uuid.UUID, Profile] = {}
    analysis_by_assessment: dict[uuid.UUID, AnalysisResult] = {}
    if assessment_ids:
        assessments_result = await db.execute(select(Assessment).where(Assessment.id.in_(assessment_ids)))
        assessments = list(assessments_result.scalars().all())
        assessments_by_id = {a.id: a for a in assessments}

        profile_ids = {a.profile_id for a in assessments}
        if profile_ids:
            profiles_result = await db.execute(select(Profile).where(Profile.id.in_(profile_ids)))
            profiles_by_id = {p.id: p for p in profiles_result.scalars().all()}

        analysis_result = await db.execute(
            select(AnalysisResult).where(AnalysisResult.assessment_id.in_(assessment_ids))
        )
        analysis_by_assessment = {}
        for a in analysis_result.scalars().all():  # KZ-405: prefer the ru row
            prev = analysis_by_assessment.get(a.assessment_id)
            if prev is None or a.locale == DEFAULT_LOCALE:
                analysis_by_assessment[a.assessment_id] = a

    items: list[AdminFeedbackListItem] = []
    for fb in feedback_rows:
        user = users_by_id.get(fb.user_id)
        assessment = assessments_by_id.get(fb.assessment_id) if fb.assessment_id else None
        profile = profiles_by_id.get(assessment.profile_id) if assessment else None
        analysis = analysis_by_assessment.get(fb.assessment_id) if fb.assessment_id else None

        scenario = None
        if profile and assessment:
            _, scenario, _, _ = _get_effective_goal_and_scenario(profile.age_group, assessment.goal)

        top_direction_name = None
        if analysis and analysis.careers:
            top_direction_name = analysis.careers[0].get("name")

        items.append(
            AdminFeedbackListItem(
                id=fb.id,
                user_id=fb.user_id,
                user_email=user.email if user else "",
                profile_name=profile.name if profile else None,
                assessment_id=fb.assessment_id,
                age_group=profile.age_group.value if profile else None,
                scenario=scenario,
                top_direction_name=top_direction_name,
                relevance_score=fb.relevance_score,
                helpful_sections=list(fb.helpful_sections),
                comment=fb.comment,
                created_at=fb.created_at,
            )
        )
    return items


async def list_feedback(
    db: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
) -> AdminFeedbackListResponse:
    total_result = await db.execute(select(func.count()).select_from(ProductFeedback))
    total = total_result.scalar_one()

    feedback_result = await db.execute(
        select(ProductFeedback)
        .order_by(ProductFeedback.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    feedback_rows = list(feedback_result.scalars().all())
    items = await _enrich_feedback_rows(db, feedback_rows)

    return AdminFeedbackListResponse(items=items, total=total, page=page, limit=limit)


def _breakdown(items: list[AdminFeedbackListItem], key_fn) -> list[FeedbackBreakdownItem]:
    groups: dict[str, list[int]] = {}
    for item in items:
        key = key_fn(item)
        if key is None:
            continue
        groups.setdefault(key, []).append(item.relevance_score)
    return [
        FeedbackBreakdownItem(key=key, count=len(scores), avg_relevance_score=round(sum(scores) / len(scores), 2))
        for key, scores in sorted(groups.items())
    ]


async def get_feedback_stats(db: AsyncSession) -> AdminFeedbackStatsResponse:
    """TZ_Profi.md §28.4: aggregate by age group / scenario / top direction.
    Feedback volume is admin-only, low-traffic data — in-Python aggregation
    over all rows (via the same enrichment `list_feedback` uses) is simpler
    and more honest than a raw SQL GROUP BY, since `scenario` isn't a stored
    column, it's derived the same way the student's own results page derives
    it."""
    feedback_result = await db.execute(select(ProductFeedback))
    feedback_rows = list(feedback_result.scalars().all())
    if not feedback_rows:
        return AdminFeedbackStatsResponse(total=0)

    items = await _enrich_feedback_rows(db, feedback_rows)

    section_counts: dict[str, int] = {}
    for item in items:
        for section in item.helpful_sections:
            section_counts[section] = section_counts.get(section, 0) + 1

    return AdminFeedbackStatsResponse(
        total=len(items),
        avg_relevance_score=round(sum(i.relevance_score for i in items) / len(items), 2),
        by_age_group=_breakdown(items, lambda i: i.age_group),
        by_scenario=_breakdown(items, lambda i: i.scenario),
        by_top_direction=_breakdown(items, lambda i: i.top_direction_name),
        helpful_section_counts=section_counts,
    )
