import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.akinator_answer_log import AkinatorAnswerLog
from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.assessment_session import AssessmentSession
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.schemas.subject_readiness import SubjectAnswerIn
from app.services import subject_readiness_service
from scripts.seed_akinator_content import seed_sections, seed_specialties
from scripts.seed_subject_questions import seed_subject_questions

# general-medicine: {"Биология": 2, "Химия": 2, "Русский язык": 1} — exactly
# 3 required subjects, so top-3 + 1 noise always yields 8 questions.
_DIRECTION_SLUG = "general-medicine"
_REQUIRED_SUBJECTS = {"Биология", "Химия", "Русский язык"}


async def _ensure_seeded(db: AsyncSession) -> None:
    section_ids, *_ = await seed_sections(db)
    await seed_specialties(db, section_ids)
    await seed_subject_questions(db)
    await db.flush()


async def _make_assessment(
    db: AsyncSession, age_group: AgeGroup, slug: str | None
) -> Assessment:
    user = User(email=f"{uuid.uuid4()}@test.local", hashed_password="x")
    db.add(user)
    await db.flush()

    profile = Profile(
        user_id=user.id, name="Test Student", age=16, grade=10,
        city="Test City", country="Test Country", language="ru",
        age_group=age_group,
    )
    db.add(profile)
    await db.flush()

    assessment = Assessment(
        profile_id=profile.id, goal=AssessmentGoal.explore,
        status=AssessmentStatus.completed, selected_direction_slug=slug,
    )
    db.add(assessment)
    await db.commit()
    return assessment


async def test_full_flow_questions_answers_result(db_session: AsyncSession):
    await _ensure_seeded(db_session)
    assessment = await _make_assessment(db_session, AgeGroup.senior, _DIRECTION_SLUG)

    questions = await subject_readiness_service.get_or_create_questions(assessment.id, db_session)
    assert len(questions) == 8

    subjects_seen = {q.subject for q in questions}
    assert _REQUIRED_SUBJECTS.issubset(subjects_seen)
    noise_subjects = subjects_seen - _REQUIRED_SUBJECTS
    assert len(noise_subjects) == 1

    answers = [
        SubjectAnswerIn(question_id=q.id, selected_option_index=3) for q in questions
    ]
    result = await subject_readiness_service.submit_answers(assessment.id, answers, db_session)

    assert {item.subject for item in result.subject_scores} == _REQUIRED_SUBJECTS
    for item in result.subject_scores:
        assert item.level == 3
        assert item.interest == 3
        assert item.is_strength is True

    # Repeat GET returns the same saved result without recomputation.
    reread = await subject_readiness_service.get_result(assessment.id, db_session)
    assert {item.subject for item in reread.subject_scores} == _REQUIRED_SUBJECTS
    assert reread.id == result.id


async def test_questions_are_stable_across_repeat_get(db_session: AsyncSession):
    await _ensure_seeded(db_session)
    assessment = await _make_assessment(db_session, AgeGroup.middle, _DIRECTION_SLUG)

    first = await subject_readiness_service.get_or_create_questions(assessment.id, db_session)
    second = await subject_readiness_service.get_or_create_questions(assessment.id, db_session)
    assert [q.id for q in first] == [q.id for q in second]


async def test_junior_gets_403(db_session: AsyncSession):
    await _ensure_seeded(db_session)
    assessment = await _make_assessment(db_session, AgeGroup.junior, _DIRECTION_SLUG)

    with pytest.raises(HTTPException) as exc_info:
        await subject_readiness_service.get_or_create_questions(assessment.id, db_session)
    assert exc_info.value.status_code == 403


async def test_unconfirmed_direction_gets_400(db_session: AsyncSession):
    await _ensure_seeded(db_session)
    assessment = await _make_assessment(db_session, AgeGroup.senior, None)

    with pytest.raises(HTTPException) as exc_info:
        await subject_readiness_service.get_or_create_questions(assessment.id, db_session)
    assert exc_info.value.status_code == 400


async def test_direction_without_subjects_required_gets_400(db_session: AsyncSession):
    section_ids, *_ = await seed_sections(db_session)
    await seed_specialties(db_session, section_ids)
    await seed_subject_questions(db_session)
    from app.models.direction import Direction

    direction = (
        await db_session.execute(select(Direction).where(Direction.slug == _DIRECTION_SLUG))
    ).scalar_one()
    direction.subjects_required = {}
    await db_session.flush()

    assessment = await _make_assessment(db_session, AgeGroup.senior, _DIRECTION_SLUG)

    with pytest.raises(HTTPException) as exc_info:
        await subject_readiness_service.get_or_create_questions(assessment.id, db_session)
    assert exc_info.value.status_code == 400


async def test_answers_must_cover_exactly_the_generated_question_set(db_session: AsyncSession):
    await _ensure_seeded(db_session)
    assessment = await _make_assessment(db_session, AgeGroup.senior, _DIRECTION_SLUG)

    questions = await subject_readiness_service.get_or_create_questions(assessment.id, db_session)
    partial_answers = [
        SubjectAnswerIn(question_id=q.id, selected_option_index=0) for q in questions[:-1]
    ]

    with pytest.raises(HTTPException) as exc_info:
        await subject_readiness_service.submit_answers(assessment.id, partial_answers, db_session)
    assert exc_info.value.status_code == 400


async def test_akinator_engine_tables_untouched_by_subject_readiness_flow(db_session: AsyncSession):
    """Hard isolation requirement: this feature must never write to
    assessment_sessions or akinator_answer_logs. Regression test rather than
    an inspection of the code, per the acceptance criteria."""
    await _ensure_seeded(db_session)

    # An assessment_session unrelated to the subject-readiness flow below —
    # its content must be byte-for-byte unchanged afterwards.
    other_assessment = await _make_assessment(db_session, AgeGroup.senior, _DIRECTION_SLUG)
    other_session = AssessmentSession(assessment_id=other_assessment.id, belief={"general-medicine": 0.9})
    db_session.add(other_session)
    await db_session.commit()
    await db_session.refresh(other_session)
    snapshot = (other_session.id, other_session.belief, other_session.step, other_session.status)

    answer_log_count_before = (
        await db_session.execute(select(func.count()).select_from(AkinatorAnswerLog))
    ).scalar_one()

    assessment = await _make_assessment(db_session, AgeGroup.senior, _DIRECTION_SLUG)
    questions = await subject_readiness_service.get_or_create_questions(assessment.id, db_session)
    answers = [SubjectAnswerIn(question_id=q.id, selected_option_index=2) for q in questions]
    await subject_readiness_service.submit_answers(assessment.id, answers, db_session)
    await subject_readiness_service.get_result(assessment.id, db_session)

    answer_log_count_after = (
        await db_session.execute(select(func.count()).select_from(AkinatorAnswerLog))
    ).scalar_one()
    assert answer_log_count_after == answer_log_count_before

    await db_session.refresh(other_session)
    assert (
        other_session.id, other_session.belief, other_session.step, other_session.status
    ) == snapshot
