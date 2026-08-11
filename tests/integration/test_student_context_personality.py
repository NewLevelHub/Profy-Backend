"""Область 9 §9.1: five new StudentContext fields (personality_profile,
personality_notes, thinking_style, motivation_top, motivation_highlights) sourced
from AnalysisResult's already-computed, display-ready Big Five/motivation layer.

Exercises `build_student_context` directly against a real, per-test-rolled-back
DB session (see tests/conftest.py) — no HTTP layer, no LLM, same style as
tests/integration/test_direction_roadmap_university.py.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services.student_context import build_student_context


async def _make_assessment(db: AsyncSession) -> Assessment:
    user = User(email=f"{uuid.uuid4()}@test.local", hashed_password="x")
    db.add(user)
    await db.flush()

    profile = Profile(
        user_id=user.id, name="Test Student", age=15, grade=9,
        city="Алматы", country="Казахстан", language="ru", age_group=AgeGroup.middle,
    )
    db.add(profile)
    await db.flush()

    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.profession)
    db.add(assessment)
    await db.flush()
    return assessment


async def test_personality_and_motivation_fields_round_trip_from_analysis(
    db_session: AsyncSession,
):
    assessment = await _make_assessment(db_session)
    db_session.add(
        AnalysisResult(
            assessment_id=assessment.id,
            summary="summary",
            profile={"R": 80.0, "I": 70.0},
            code=["R", "I"],
            strengths=["R"],
            weaknesses=["C"],
            # admin-only raw layers — must NOT leak into StudentContext (§9.1)
            big_five={"N": 32.0, "E": 55.0},
            motivation={"interest": 6},
            # safe, display-ready derived layer — this is what StudentContext gets
            personality_profile={"emotional_stability": 68.0, "conscientiousness": 40.0},
            personality_notes={
                "conscientiousness": "тебе сложно долго держать фокус на одном деле",
                "emotional_stability": "ты обычно сохраняешь спокойствие даже в стрессе",
            },
            thinking_style={"creative_think": 72.0, "systematic": 55.0},
            motivation_top=["interest", "creation"],
            motivation_highlights=["тебя драйвит решать нестандартные задачи"],
        )
    )
    await db_session.flush()

    context = await build_student_context(assessment.id, db_session)

    assert context is not None
    assert context.personality_profile == {
        "emotional_stability": 68.0,
        "conscientiousness": 40.0,
    }
    assert context.personality_notes == {
        "conscientiousness": "тебе сложно долго держать фокус на одном деле",
        "emotional_stability": "ты обычно сохраняешь спокойствие даже в стрессе",
    }
    assert context.thinking_style == {"creative_think": 72.0, "systematic": 55.0}
    assert context.motivation_top == ["interest", "creation"]
    assert context.motivation_highlights == ["тебя драйвит решать нестандартные задачи"]

    # StudentContext has no big_five/motivation fields at all — admin-only raw
    # scores must never reach a field the LLM prompt can read (§9.1).
    assert not hasattr(context, "big_five")
    assert not hasattr(context, "motivation")


async def test_personality_and_motivation_fields_empty_without_analysis(
    db_session: AsyncSession,
):
    assessment = await _make_assessment(db_session)

    context = await build_student_context(assessment.id, db_session)

    assert context is not None
    assert context.personality_profile == {}
    assert context.personality_notes == {}
    assert context.thinking_style == {}
    assert context.motivation_top == []
    assert context.motivation_highlights == []
