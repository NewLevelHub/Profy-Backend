import uuid
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.known_profession_quiz import KnownProfessionQuiz
from app.models.known_profession_quiz_log import KnownProfessionQuizLog
from app.services import direction_service

MatchVerdict = Literal["strong", "partial", "weak"]


async def get_quiz(leaf_slug: str, db: AsyncSession) -> KnownProfessionQuiz | None:
    result = await db.execute(
        select(KnownProfessionQuiz).where(KnownProfessionQuiz.leaf_slug == leaf_slug)
    )
    return result.scalar_one_or_none()


def score_answers(
    questions: list[dict], answers: dict[str, int]
) -> tuple[int, MatchVerdict]:
    score = 0
    max_score = 0
    for question in questions:
        max_score += 2
        option_index = answers.get(question["id"])
        if option_index is None:
            continue
        options = question["options"]
        if 0 <= option_index < len(options):
            score += options[option_index]["fit_score"]

    percent = round((score / max_score) * 100) if max_score else 0
    if percent >= 70:
        verdict: MatchVerdict = "strong"
    elif percent >= 40:
        verdict = "partial"
    else:
        verdict = "weak"
    return percent, verdict


async def finalize(
    profile_id: uuid.UUID,
    direction_slug: str,
    answers: dict[str, int],
    db: AsyncSession,
) -> tuple[Assessment, int, MatchVerdict]:
    direction = await direction_service.get_direction_by_slug(direction_slug, db)
    if direction is None or not direction.is_leaf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Direction not found")

    quiz = await get_quiz(direction_slug, db)
    if quiz is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No known-profession quiz for this direction",
        )

    percent, verdict = score_answers(quiz.questions, answers)

    # Same "only one current assessment" invariant enforced in
    # assessment_service.create_assessment — an unfinished main-quiz attempt
    # shouldn't linger as "current" once this flow produces a real result.
    existing_result = await db.execute(
        select(Assessment).where(
            Assessment.profile_id == profile_id,
            Assessment.status == AssessmentStatus.in_progress,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        existing.status = AssessmentStatus.abandoned

    # No AssessmentSession is created here — this flow never runs the
    # belief-walk engine, so there is no session/belief to persist. See
    # known-profession-redesign notes: result_service.get_result and
    # roadmap_builder already tolerate a sessionless Assessment.
    assessment = Assessment(
        profile_id=profile_id,
        goal=AssessmentGoal.known,
        status=AssessmentStatus.completed,
        selected_direction_slug=direction_slug,
        completed_at=func.now(),
    )
    db.add(assessment)
    await db.flush()

    log = KnownProfessionQuizLog(
        assessment_id=assessment.id,
        leaf_slug=direction_slug,
        answers=[{"question_id": qid, "option_index": idx} for qid, idx in answers.items()],
        percent=percent,
        verdict=verdict,
    )
    db.add(log)

    await db.commit()
    await db.refresh(assessment)
    return assessment, percent, verdict
