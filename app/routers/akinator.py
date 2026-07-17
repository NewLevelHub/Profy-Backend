import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.akinator_question import AkinatorQuestion
from app.models.assessment import Assessment
from app.models.direction import Direction
from app.models.assessment_session import AssessmentSession
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.schemas.akinator_session import (
    AkinatorAnswerRequest,
    AkinatorFeedbackRequest,
    AkinatorFeedbackResponse,
    AkinatorOption,
    AkinatorTurnResponse,
    AkinatorRejectAllRequest,
    AkinatorResolveRequest,
    NextQuestionResponse,
    RevealLeaf,
    RevealResponse,
)
from app.services import akinator_report_service, akinator_session_service, cluster_resolver_service
from app.services.akinator_engine import StopDecision
from app.services.akinator_session_service import SessionTurn
from app.services.profile_service import get_profile

router = APIRouter(tags=["akinator"])


async def _require_owned_assessment(
    assessment_id: uuid.UUID, current_user: User, db: AsyncSession
) -> AgeGroup:
    """Same 404-then-403 ownership pattern as assessment_service.complete_block."""
    profile = await get_profile(current_user.id, db)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    row_result = await db.execute(
        select(Assessment, Profile.age_group)
        .join(Profile, Assessment.profile_id == Profile.id)
        .where(Assessment.id == assessment_id)
    )
    row = row_result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    assessment, age_group = row
    if assessment.profile_id != profile.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    session_result = await db.execute(
        select(AssessmentSession).where(AssessmentSession.assessment_id == assessment_id)
    )
    if session_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Этот тест не использует диалоговый поток акинатора",
        )

    return age_group


def _question_text(question: AkinatorQuestion, age_group: AgeGroup) -> str:
    if age_group == AgeGroup.junior and question.text_junior:
        return question.text_junior
    return question.text


async def _reveal_response(
    decision: StopDecision,
    belief: dict[str, float],
    rejected_leaves: list[str],
    age_group: AgeGroup,
    db: AsyncSession,
) -> RevealResponse:
    # Axis-profile weighting for the honest "couldn't narrow it down" summary
    # is only needed on that path — skip the extra query otherwise.
    leaf_profiles = None
    if decision.status == "reveal_cluster" and decision.reason == "ceiling":
        leaf_profiles = await akinator_session_service._leaf_profiles_for(db, belief)

    report = akinator_report_service.build_reveal_report(
        decision, belief, rejected_leaves, leaf_profiles=leaf_profiles
    )

    all_slugs = [*report.leaves, *report.backups]
    result = await db.execute(
        select(Direction).where(
            Direction.slug.in_(all_slugs),
            Direction.is_leaf.is_(True)
        )
    )
    leaves_by_slug = {d.slug: d for d in result.scalars().all()}

    section_ids = {d.parent_id for d in leaves_by_slug.values() if d.parent_id is not None}
    sections_result = await db.execute(select(Direction).where(Direction.id.in_(section_ids)))
    section_name_by_id = {s.id: s.name for s in sections_result.scalars().all()}

    # junior gets the friendlier label_junior where set (e.g. "Хирург" -> "Врач")
    # instead of the technical profession name — same fallback pattern as
    # _question_text's text_junior.
    def to_leaves(slugs: list[str]) -> list[RevealLeaf]:
        leaves = []
        for slug in slugs:
            direction = leaves_by_slug.get(slug)
            if direction is None:
                continue
            name = (
                direction.label_junior
                if age_group == AgeGroup.junior and direction.label_junior
                else direction.name
            )
            section_name = section_name_by_id.get(direction.parent_id, "")
            leaves.append(RevealLeaf(
                slug=slug, name=name, direction=section_name, description=direction.description,
            ))
        return leaves

    reveal_status: Literal["single", "cluster", "inconclusive"] = {
        "confident": "single",
        "uncertain": "cluster",
        "inconclusive": "inconclusive",
    }[report.kind]
    return RevealResponse(
        status=reveal_status,
        leaves=to_leaves(report.leaves),
        backups=to_leaves(report.backups),
        message=report.message,
        strengths=report.strengths,
    )


async def _turn_response(
    turn: SessionTurn, age_group: AgeGroup, db: AsyncSession
) -> NextQuestionResponse | RevealResponse:
    if turn.next_question is not None:
        question = turn.next_question
        options = [
            AkinatorOption(index=i, text=option.get("text", ""))
            for i, option in enumerate(question.options)
        ]
        return NextQuestionResponse(
            question_id=question.id, text=_question_text(question, age_group), options=options
        )
    return await _reveal_response(
        turn.decision, turn.session.belief, turn.session.rejected_leaves, age_group, db
    )


@router.post("/{assessment_id}/akinator/start", response_model=AkinatorTurnResponse)
async def start_akinator(
    assessment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NextQuestionResponse | RevealResponse:
    age_group = await _require_owned_assessment(assessment_id, current_user, db)
    try:
        turn = await akinator_session_service.start_session(assessment_id, age_group, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return await _turn_response(turn, age_group, db)


@router.post("/{assessment_id}/akinator/answer", response_model=AkinatorTurnResponse)
async def answer_akinator(
    assessment_id: uuid.UUID,
    data: AkinatorAnswerRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NextQuestionResponse | RevealResponse:
    age_group = await _require_owned_assessment(assessment_id, current_user, db)
    try:
        turn = await akinator_session_service.submit_answer(
            assessment_id, data.question_id, data.selected_option_index, age_group, db
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return await _turn_response(turn, age_group, db)


@router.post("/{assessment_id}/akinator/feedback", response_model=AkinatorFeedbackResponse)
async def submit_akinator_feedback(
    assessment_id: uuid.UUID,
    data: AkinatorFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AkinatorFeedbackResponse:
    await _require_owned_assessment(assessment_id, current_user, db)
    try:
        await akinator_session_service.submit_feedback(
            assessment_id, data.liked, data.note, db, direction_slug=data.direction_slug
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AkinatorFeedbackResponse()


@router.post("/{assessment_id}/akinator/reject/{leaf_slug}", response_model=AkinatorTurnResponse)
async def reject_akinator_leaf(
    assessment_id: uuid.UUID,
    leaf_slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NextQuestionResponse | RevealResponse:
    age_group = await _require_owned_assessment(assessment_id, current_user, db)
    try:
        turn = await akinator_session_service.reject_leaf(assessment_id, leaf_slug, age_group, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return await _turn_response(turn, age_group, db)


@router.post("/{assessment_id}/akinator/reject-all", response_model=AkinatorTurnResponse)
async def reject_akinator_leaves(
    assessment_id: uuid.UUID,
    data: AkinatorRejectAllRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NextQuestionResponse | RevealResponse:
    age_group = await _require_owned_assessment(assessment_id, current_user, db)
    try:
        turn = await akinator_session_service.reject_leaves(
            assessment_id, data.leaf_slugs, age_group, db
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return await _turn_response(turn, age_group, db)


@router.post("/{assessment_id}/akinator/resolve", response_model=AkinatorTurnResponse)
async def resolve_cluster(
    assessment_id: uuid.UUID,
    data: AkinatorResolveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NextQuestionResponse | RevealResponse:
    age_group = await _require_owned_assessment(assessment_id, current_user, db)
    try:
        turn = await cluster_resolver_service.resolve_cluster_turn(
            assessment_id,
            data.question_id,
            data.selected_option_index,
            age_group,
            db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return await _turn_response(turn, age_group, db)
