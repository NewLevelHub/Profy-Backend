import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import roadmap_builder
from scripts.seed_akinator_content import seed_questions, seed_sections, seed_specialties


async def _ensure_seeded(db: AsyncSession) -> None:
    section_ids, *_ = await seed_sections(db)
    await seed_specialties(db, section_ids)
    await seed_questions(db)
    await db.flush()


async def _make_completed_assessment(
    db: AsyncSession, goal: AssessmentGoal, age_group: AgeGroup, slug: str,
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
        profile_id=profile.id, goal=goal,
        status=AssessmentStatus.completed, selected_direction_slug=slug,
    )
    db.add(assessment)
    await db.commit()
    return assessment


async def test_direction_roadmap_access_allowed_for_university_goal(db_session: AsyncSession):
    """Regression test: direction roadmap generation is goal-agnostic — a
    student whose test goal was "поступление" (university) must be able to
    build one just like any other goal. There is no separate program-specific
    plan feature in this codebase to defer to instead."""
    await _ensure_seeded(db_session)
    assessment = await _make_completed_assessment(
        db_session, AssessmentGoal.university, AgeGroup.senior, "architect"
    )

    result_assessment, direction = await roadmap_builder._require_direction_roadmap_access(
        assessment.id, "architect", db_session
    )

    assert result_assessment.id == assessment.id
    assert direction.slug == "architect"


async def test_direction_roadmap_access_rejects_junior(db_session: AsyncSession):
    await _ensure_seeded(db_session)
    assessment = await _make_completed_assessment(
        db_session, AssessmentGoal.explore, AgeGroup.junior, "architect"
    )

    with pytest.raises(Exception) as exc_info:
        await roadmap_builder._require_direction_roadmap_access(
            assessment.id, "architect", db_session
        )
    assert exc_info.value.status_code == 403


async def test_direction_roadmap_access_rejects_wrong_slug(db_session: AsyncSession):
    await _ensure_seeded(db_session)
    assessment = await _make_completed_assessment(
        db_session, AssessmentGoal.explore, AgeGroup.senior, "architect"
    )

    with pytest.raises(Exception) as exc_info:
        await roadmap_builder._require_direction_roadmap_access(
            assessment.id, "software-engineer", db_session
        )
    assert exc_info.value.status_code == 400
