"""Shared setup for the psychologist review gate tests (PRO-337) — not a
test module itself (no `test_` prefix, pytest doesn't collect it)."""

import uuid
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.psychologist_assignment import PsychologistStudentAssignment
from app.models.question import Question, QuestionInstrument
from app.models.user import User
from app.models.user_response import UserResponse
from app.services import assessment_shared, email_service, llm_client, motivation_service

STUDENT_NAME = "Айгерим"


async def make_student_assessment(db_session: AsyncSession, student: User) -> Assessment:
    profile = Profile(
        user_id=student.id, name=STUDENT_NAME, age=16, grade=10, city="Алматы",
        country="Казахстан", language="ru", age_group=AgeGroup.senior,
    )
    db_session.add(profile)
    await db_session.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db_session.add(assessment)
    await db_session.flush()
    return assessment


async def answer_legacy_big_five(
    db_session: AsyncSession, assessment: Assessment
) -> None:
    """Populate a complete historical Big Five attempt for legacy-only tests."""
    question_ids = (
        await db_session.execute(
            select(Question.id).where(
                Question.instrument == QuestionInstrument.big_five
            )
        )
    ).scalars().all()
    assert question_ids, "seeded Big Five bank is required for the legacy fixture"
    db_session.add_all(
        [
            UserResponse(
                assessment_id=assessment.id,
                question_id=question_id,
                answer_value=4,
            )
            for question_id in question_ids
        ]
    )
    await db_session.flush()


async def make_other_student(db_session: AsyncSession) -> User:
    user = User(
        email=f"{uuid.uuid4()}@example.test", hashed_password="x", is_active=True, is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


def force_complete_senior(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same shortcut as test_report_cache_resilience: every completeness
    counter reports "done" and the LLM is off, so build_report runs the real
    scoring + fallback narrative on an empty answer set. Belbin + АСТУР are
    also required now (assessment_shared.belbin_and_astur_completed) — none
    of these review-gate tests seed either, so that's patched too."""
    monkeypatch.setattr(assessment_shared, "likert_answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(assessment_shared, "likert_total_questions", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "total_triplets", AsyncMock(return_value=1))
    monkeypatch.setattr(assessment_shared, "belbin_and_astur_completed", AsyncMock(return_value=True))
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)


def capture_emails(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    pending = AsyncMock()
    published = AsyncMock()
    monkeypatch.setattr(email_service, "send_review_pending_email", pending)
    monkeypatch.setattr(email_service, "send_result_published_email", published)
    return {"pending": pending, "published": published}


async def generate(
    client: httpx.AsyncClient, headers: dict[str, str], assessment: Assessment
) -> httpx.Response:
    return await client.post(
        "/api/v1/result/generate", json={"assessment_id": str(assessment.id)}, headers=headers
    )


async def assign(
    db_session: AsyncSession, psychologist: User, student: User
) -> PsychologistStudentAssignment:
    """Links psychologist ↔ student straight in the DB. In production the
    psychologist self-claims (`POST /psychologist/students/{id}/claim`), but
    that flow has its own eligibility rules (unclaimed student, has a
    result) that these tests aren't about — they only need the link."""
    assignment = PsychologistStudentAssignment(psychologist_id=psychologist.id, student_id=student.id)
    db_session.add(assignment)
    await db_session.flush()
    return assignment


async def stored_result(db_session: AsyncSession, assessment_id: uuid.UUID) -> AnalysisResult:
    result = await db_session.execute(
        select(AnalysisResult)
        .where(AnalysisResult.assessment_id == assessment_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()
