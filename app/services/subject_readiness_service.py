import random
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment
from app.models.direction import Direction
from app.models.profile import AgeGroup, Profile
from app.models.subject_question import SubjectQuestion
from app.models.subject_readiness_session import SubjectReadinessSession, SubjectReadinessStatus
from app.schemas.subject_readiness import (
    SubjectAnswerIn,
    SubjectQuestionOption,
    SubjectQuestionOut,
    SubjectReadinessResult,
    SubjectScoreItem,
)
from app.services import direction_service

# Top N subjects (by Direction.subjects_required weight) that actually count
# towards the student's result, plus one unrelated "noise" subject so the
# question set doesn't give away what's being measured (see plan doc).
REQUIRED_SUBJECT_COUNT = 3
NOISE_SUBJECT_COUNT = 1


async def _require_subject_readiness_access(
    assessment_id: uuid.UUID, db: AsyncSession
) -> tuple[Assessment, Direction]:
    """Mirrors roadmap_builder._require_direction_roadmap_access — duplicated
    rather than imported so this feature stays fully self-contained and never
    touches the Akinator engine or its models."""
    assessment = (
        await db.execute(select(Assessment).where(Assessment.id == assessment_id))
    ).scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    profile = (
        await db.execute(select(Profile).where(Profile.id == assessment.profile_id))
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    if profile.age_group == AgeGroup.junior:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Эта возможность доступна с 10 лет",
        )

    if assessment.selected_direction_slug is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сначала выберите направление в тесте",
        )

    direction = await direction_service.get_direction_by_slug(
        assessment.selected_direction_slug, db
    )
    if direction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Direction not found")

    if not direction.subjects_required:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для этого направления квиз по предметам пока недоступен",
        )

    return assessment, direction


def _top_subjects(direction: Direction) -> list[str]:
    ranked = sorted(
        direction.subjects_required.items(), key=lambda kv: (-kv[1], kv[0])
    )
    return [name for name, _ in ranked[: REQUIRED_SUBJECT_COUNT]]


async def _pick_noise_subject(direction: Direction, db: AsyncSession) -> str | None:
    all_subjects = {
        row[0] for row in (await db.execute(select(SubjectQuestion.subject).distinct())).all()
    }
    own_subjects = set(direction.subjects_required.keys())

    # Prefer a subject required by a sibling specialty in the same section
    # (e.g. Физика for a software-engineer, whose section-mates are
    # data-science/it-infrastructure-security) — still not what *this*
    # direction measures, but a plausible neighbour instead of a total
    # non-sequitur like География for a programmer. Only fall back to the
    # full catalog when the section is too small/homogeneous to offer one.
    sibling_subjects: set[str] = set()
    if direction.parent_id is not None:
        sibling_rows = (
            await db.execute(
                select(Direction.subjects_required).where(
                    Direction.parent_id == direction.parent_id,
                    Direction.id != direction.id,
                )
            )
        ).scalars().all()
        for subjects_required in sibling_rows:
            sibling_subjects.update((subjects_required or {}).keys())

    candidates = list((sibling_subjects & all_subjects) - own_subjects)
    if not candidates:
        candidates = list(all_subjects - own_subjects)
    if not candidates:
        return None
    return random.choice(candidates)


def _to_question_out(question: SubjectQuestion) -> SubjectQuestionOut:
    options = [
        SubjectQuestionOption(text=opt["text"], index=i)
        for i, opt in enumerate(question.options)
    ]
    return SubjectQuestionOut(
        id=question.id,
        subject=question.subject,
        kind=question.kind.value,
        text=question.text,
        options=options,
    )


def _to_result_schema(session: SubjectReadinessSession) -> SubjectReadinessResult:
    items = [
        SubjectScoreItem(subject=subject, **scores)
        for subject, scores in session.subject_scores.items()
    ]
    return SubjectReadinessResult(
        id=session.id,
        assessment_id=session.assessment_id,
        direction_slug=session.direction_slug,
        subject_scores=items,
        completed_at=session.completed_at,
    )


async def _questions_by_ids(question_ids: list[str], db: AsyncSession) -> list[SubjectQuestion]:
    ids = [uuid.UUID(qid) for qid in question_ids]
    rows = (
        await db.execute(select(SubjectQuestion).where(SubjectQuestion.id.in_(ids)))
    ).scalars().all()
    by_id = {str(row.id): row for row in rows}
    return [by_id[qid] for qid in question_ids if qid in by_id]


async def get_or_create_questions(
    assessment_id: uuid.UUID, db: AsyncSession
) -> list[SubjectQuestionOut]:
    _, direction = await _require_subject_readiness_access(assessment_id, db)

    # assessment_id is unique on this table — at most one session, ever, per
    # assessment (in_progress or completed), so this covers both cases.
    existing = (
        await db.execute(
            select(SubjectReadinessSession).where(
                SubjectReadinessSession.assessment_id == assessment_id
            )
        )
    ).scalar_one_or_none()

    if existing is not None and existing.status == SubjectReadinessStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Квиз уже пройден для этого направления",
        )

    if existing is not None:
        questions = await _questions_by_ids(existing.question_ids, db)
        return [_to_question_out(q) for q in questions]

    top_subjects = _top_subjects(direction)
    noise_subject = await _pick_noise_subject(direction, db)
    subjects_for_quiz = top_subjects + ([noise_subject] if noise_subject else [])

    rows = (
        await db.execute(
            select(SubjectQuestion).where(SubjectQuestion.subject.in_(subjects_for_quiz))
        )
    ).scalars().all()
    rows = list(rows)
    random.shuffle(rows)

    session = SubjectReadinessSession(
        assessment_id=assessment_id,
        direction_slug=direction.slug,
        question_ids=[str(row.id) for row in rows],
    )
    db.add(session)
    await db.commit()

    return [_to_question_out(q) for q in rows]


async def submit_answers(
    assessment_id: uuid.UUID, answers: list[SubjectAnswerIn], db: AsyncSession
) -> SubjectReadinessResult:
    _, direction = await _require_subject_readiness_access(assessment_id, db)

    session = (
        await db.execute(
            select(SubjectReadinessSession).where(
                SubjectReadinessSession.assessment_id == assessment_id
            )
        )
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not started")
    if session.status == SubjectReadinessStatus.completed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quiz already submitted")

    submitted_ids = {str(a.question_id) for a in answers}
    if submitted_ids != set(session.question_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Answers must cover exactly the generated question set",
        )

    questions = await _questions_by_ids(session.question_ids, db)
    questions_by_id = {str(q.id): q for q in questions}

    raw_scores: dict[str, dict[str, int]] = {}
    for answer in answers:
        question = questions_by_id[str(answer.question_id)]
        if not 0 <= answer.selected_option_index < len(question.options):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid option index")
        score = question.options[answer.selected_option_index]["score"]
        subject_bucket = raw_scores.setdefault(question.subject, {})
        subject_bucket[question.kind.value] = score

    subject_scores = {
        subject: {
            "level": scores.get("level", 0),
            "interest": scores.get("interest", 0),
            "is_strength": scores.get("level", 0) >= 2 and scores.get("interest", 0) >= 2,
        }
        for subject, scores in raw_scores.items()
        if subject in direction.subjects_required
    }

    session.answers = [
        {"question_id": str(a.question_id), "selected_option_index": a.selected_option_index}
        for a in answers
    ]
    session.subject_scores = subject_scores
    session.status = SubjectReadinessStatus.completed
    session.completed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(session)

    return _to_result_schema(session)


async def get_result(assessment_id: uuid.UUID, db: AsyncSession) -> SubjectReadinessResult:
    await _require_subject_readiness_access(assessment_id, db)

    session = (
        await db.execute(
            select(SubjectReadinessSession).where(
                SubjectReadinessSession.assessment_id == assessment_id,
                SubjectReadinessSession.status == SubjectReadinessStatus.completed,
            )
        )
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found")

    return _to_result_schema(session)
