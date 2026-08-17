"""Область 8: university folded into the direction-roadmap access gate + the
DB-backed half of `_university_requirements_for` (see
tests/unit/test_university_requirements_mapping.py for the pure-mapping half).

Exercises `roadmap_builder` service functions directly against a real,
per-test-rolled-back DB session (see tests/conftest.py) — no HTTP layer, no
LLM call, since neither is what changed here.
"""
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.direction import Direction
from app.models.direction_inquiry import DirectionInquiry
from app.models.profile import AgeGroup, Profile
from app.models.program import Program
from app.models.university import University
from app.models.user import User
from app.services import roadmap_builder

SLUG = "test-university-direction-8"


async def _make_assessment(
    db: AsyncSession, goal: AssessmentGoal, age_group: AgeGroup = AgeGroup.senior
) -> Assessment:
    user = User(email=f"{uuid.uuid4()}@test.local", hashed_password="x")
    db.add(user)
    await db.flush()

    profile = Profile(
        user_id=user.id, name="Test Student", age=16, grade=10,
        city="Алматы", country="Казахстан", language="ru", age_group=age_group,
    )
    db.add(profile)
    await db.flush()

    assessment = Assessment(profile_id=profile.id, goal=goal)
    db.add(assessment)
    await db.flush()
    return assessment


async def test_university_goal_passes_the_access_gate(db_session: AsyncSession):
    """Область 8's core change: goal == university used to 400 here
    ("используется план по программе университета"); it must now pass through
    the same gate as profession/explore/unsure."""
    assessment = await _make_assessment(db_session, AssessmentGoal.university)

    direction = Direction(name="Test Direction", slug=SLUG, holland_code="RIA")
    db_session.add(direction)

    db_session.add(DirectionInquiry(
        assessment_id=assessment.id, direction_slug=SLUG,
        readiness="ready", fit_summary="fits", note="note",
    ))
    await db_session.flush()

    result_assessment, result_direction = await roadmap_builder._require_direction_roadmap_access(
        assessment.id, SLUG, db_session
    )

    assert result_assessment.id == assessment.id
    assert result_direction.slug == SLUG


async def test_university_goal_still_blocked_for_junior(db_session: AsyncSession):
    """The gate drops the university-specific exclusion but keeps the rest:
    junior is still blocked, for university same as for every other goal."""
    assessment = await _make_assessment(
        db_session, AssessmentGoal.university, age_group=AgeGroup.junior
    )

    with pytest.raises(HTTPException) as exc_info:
        await roadmap_builder._require_direction_roadmap_access(assessment.id, SLUG, db_session)

    assert exc_info.value.status_code == 403


async def test_university_goal_skips_inquiry_check(db_session: AsyncSession):
    """University goal skips the inquiry check, so it passes even with no DirectionInquiry row."""
    original_required = roadmap_builder._INQUIRY_REQUIRED
    roadmap_builder._INQUIRY_REQUIRED = True
    try:
        assessment = await _make_assessment(db_session, AssessmentGoal.university)
        direction = Direction(name="Test Direction", slug=SLUG, holland_code="RIA")
        db_session.add(direction)
        await db_session.flush()

        res_assessment, res_direction = await roadmap_builder._require_direction_roadmap_access(
            assessment.id, SLUG, db_session
        )
        assert res_assessment.id == assessment.id
        assert res_direction.slug == SLUG
    finally:
        roadmap_builder._INQUIRY_REQUIRED = original_required


async def test_university_requirements_for_real_seeded_rows(db_session: AsyncSession):
    university = University(name="Test University", country="Казахстан", city="Алматы")
    db_session.add(university)
    await db_session.flush()

    program = Program(
        university_id=university.id,
        name="Test Program",
        profession_slugs=[SLUG],
        language="ru",
        requirements={
            "exams": ["ЕНТ"],
            "min_ielts": 6.0,
            "needs_portfolio": False,
            "needs_essay": True,
        },
        deadlines={"application_close": "2026-12-01"},
        grants=[{"name": "Grant", "amount": "100%", "conditions": "..."}],
    )
    db_session.add(program)
    await db_session.flush()

    reqs = await roadmap_builder._university_requirements_for(SLUG, db_session)

    assert len(reqs) == 1
    req = reqs[0]
    assert req.university_name == "Test University"
    assert req.city == "Алматы"
    assert req.application_deadline == "2026-12-01"
    assert req.language_level == "IELTS 6.0"
    assert req.portfolio_needed is False
    assert req.required_documents == ["Мотивационное эссе"]
    assert req.grants[0].name == "Grant"


async def test_university_requirements_empty_for_slug_with_no_programs(db_session: AsyncSession):
    reqs = await roadmap_builder._university_requirements_for(
        "no-programs-for-this-slug-xyz", db_session
    )
    assert reqs == []
