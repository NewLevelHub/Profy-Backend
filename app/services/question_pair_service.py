"""Forced-choice-pair format — junior (6-9, TZ_Profi.md §13 bans Likert
outright) gets its whole test this way, shown on its own screen. Middle
(10-13) gets a subset of its own tier-exclusive questions woven into the
ordinary Likert flow instead, to break up monotony (TZ_Profi.md §14) without
abandoning Likert (still fine for that age). `QuestionPair.age_tier` is an
exact match, unlike `Question.age_tier` (checked via visible_tiers(),
cumulative) — a junior pair is never returned to a middle profile or vice
versa.

A pair pick is written as two ordinary `UserResponse` rows (picked=5,
other=1) — riasec_service/bigfive_service and the Likert-completion
counters in assessment_shared read `UserResponse` regardless of whether it
came from a Likert answer or a pair pick, so neither of those needed any
changes for this format to work.
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.assessment import Assessment, AssessmentStatus
from app.models.profile import AgeGroup
from app.models.question import Question, QuestionInstrument
from app.models.question_pair import QuestionPair
from app.models.user_response import UserResponse
from app.schemas.question_pair import (
    PairAnswerItem,
    QuestionPairItem,
    QuestionPairOption,
    SubmitPairAnswersResponse,
)
from app.services import assessment_shared

_PICKED_VALUE = 5
_OTHER_VALUE = 1


def _to_option(
    question: Question, override_text: str | None = None, override_icon: str | None = None
) -> QuestionPairOption:
    return QuestionPairOption(
        id=question.id,
        text=override_text or question.short_text or question.text,
        icon=override_icon or question.icon,
        riasec_type=question.riasec_type,
        bigfive_domain=question.bigfive_domain,
        mi_category=question.mi_category,
    )


async def get_pairs(db: AsyncSession, age_group: AgeGroup) -> list[QuestionPairItem]:
    question_a = aliased(Question)
    question_b = aliased(Question)
    query = (
        select(QuestionPair, question_a, question_b)
        .join(question_a, QuestionPair.question_a_id == question_a.id)
        .join(question_b, QuestionPair.question_b_id == question_b.id)
        .where(QuestionPair.age_tier == age_group)
        .order_by(QuestionPair.pair_index)
    )
    if age_group == AgeGroup.junior:
        # Junior's RIASEC content is retired in favor of the MI instrument
        # (TZ_Profi.md §4.1 — no career orientation for 6-9-year-olds); old
        # junior-tagged `riasec` QuestionPair rows are left in the DB but
        # excluded here rather than migrated/deleted. MI itself is answered
        # as plain Likert now (product override: ipsative pairing between
        # unrelated MI categories made an already-weak construct worse — see
        # question_service.get_all_questions), so only Big Five stays paired.
        query = query.where(QuestionPair.instrument == QuestionInstrument.big_five)
    result = await db.execute(query)
    return [
        QuestionPairItem(
            pair_index=pair.pair_index,
            instrument=pair.instrument,
            frame=pair.frame,
            display_order=min(q_a.order, q_b.order),
            option_a=_to_option(q_a, pair.option_a_text, pair.option_a_icon),
            option_b=_to_option(q_b, pair.option_b_text, pair.option_b_icon),
        )
        for pair, q_a, q_b in result.all()
    ]


async def submit_pair_answers(
    assessment_id: uuid.UUID,
    answers: list[PairAnswerItem],
    current_profile_id: uuid.UUID,
    db: AsyncSession,
) -> SubmitPairAnswersResponse:
    row_result = await db.execute(select(Assessment).where(Assessment.id == assessment_id))
    assessment = row_result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    if assessment.profile_id != current_profile_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    age_group = await assessment_shared.get_profile_age_group(assessment.profile_id, db)

    pair_indexes = [item.pair_index for item in answers]
    pairs_result = await db.execute(
        select(QuestionPair).where(QuestionPair.pair_index.in_(pair_indexes))
    )
    pairs_by_index = {p.pair_index: p for p in pairs_result.scalars().all()}

    response_rows: list[dict] = []
    for item in answers:
        pair = pairs_by_index.get(item.pair_index)
        if pair is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Pair {item.pair_index} not found",
            )
        if item.picked_question_id not in (pair.question_a_id, pair.question_b_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Question {item.picked_question_id} is not part of pair {item.pair_index}",
            )
        other_id = pair.question_b_id if item.picked_question_id == pair.question_a_id else pair.question_a_id
        response_rows.append({
            "id": uuid.uuid4(), "assessment_id": assessment_id,
            "question_id": item.picked_question_id, "answer_value": _PICKED_VALUE,
        })
        response_rows.append({
            "id": uuid.uuid4(), "assessment_id": assessment_id,
            "question_id": other_id, "answer_value": _OTHER_VALUE,
        })

    is_retake = assessment.status == AssessmentStatus.completed
    if response_rows:
        stmt = pg_insert(UserResponse).values(response_rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_user_response_assessment_question",
            set_={"answer_value": stmt.excluded.answer_value},
        )
        await db.execute(stmt)

    if is_retake:
        assessment.status = AssessmentStatus.in_progress
        assessment.completed_at = None
        redis = assessment_shared.get_redis()
        await assessment_shared.invalidate_retake(assessment, db, redis)

    answered = await assessment_shared.likert_answered_count(assessment_id, db)
    total = await assessment_shared.likert_total_questions(db, age_group)
    # Same caveat as assessment_service.submit_answers: this phase being done
    # does not flip assessment.status — motivation_service does that once
    # both phases are confirmed answered.
    completed = total > 0 and answered >= total

    await db.commit()

    return SubmitPairAnswersResponse(answered_count=answered, total=total, completed=completed)
