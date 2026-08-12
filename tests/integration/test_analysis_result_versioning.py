"""Legacy rows (anything written before the v2 narrative pipeline exists —
which right now is every row, since nothing populates strength_cards/
thinking_style_notes yet) must be explicitly report_version=1 *in storage*.
Reading code must never infer "this is v2" from strength_cards happening to
be non-empty — the version column is the only source of truth for that."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.schemas.admin_result import AdminAnalysisResultResponse


async def _make_assessment(db: AsyncSession) -> Assessment:
    user = User(email=f"{uuid.uuid4()}@example.test", hashed_password="x")
    db.add(user)
    await db.flush()
    profile = Profile(
        user_id=user.id, name="Тест", age=16, grade=10, city="Алматы",
        country="Казахстан", language="ru", age_group=AgeGroup.senior,
    )
    db.add(profile)
    await db.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()
    return assessment


def _minimal_analysis_kwargs(assessment_id: uuid.UUID) -> dict:
    return dict(
        assessment_id=assessment_id,
        summary="s",
        profile={},
        code=[],
        meta={"differentiation": 0.0, "consistency": "high", "aversion": {}},
        careers=[],
        strengths=[],
        weaknesses=[],
        development_plan={"reinforce": [], "compensate": []},
        big_five={},
        thinking_style={"creative_think": 0.0, "systematic": 0.0, "strategic": 0.0, "practical": 0.0},
        personality_highlights=[],
        motivation={},
        motivation_top=[],
        motivation_highlights=[],
        personality_profile={},
        personality_notes={},
    )


async def test_row_written_without_report_version_defaults_to_legacy_1(
    db_session: AsyncSession,
) -> None:
    """The ORM-level `default=1` / DB `server_default` — not client code
    remembering to pass a value — is what makes this safe."""
    assessment = await _make_assessment(db_session)
    analysis = AnalysisResult(**_minimal_analysis_kwargs(assessment.id))
    db_session.add(analysis)
    await db_session.flush()
    await db_session.refresh(analysis)

    assert analysis.report_version == 1
    assert analysis.strength_cards == []
    assert analysis.thinking_style_notes == []

    validated = AdminAnalysisResultResponse.model_validate(analysis)
    assert validated.report_version == 1
    assert validated.strength_cards == []
    assert validated.thinking_style_notes == []


async def test_v2_row_saves_version_together_with_narrative_fields(
    db_session: AsyncSession,
) -> None:
    assessment = await _make_assessment(db_session)
    analysis = AnalysisResult(
        **_minimal_analysis_kwargs(assessment.id),
        report_version=2,
        strength_cards=[{"title": "Любишь докапываться до сути", "description": "..."}],
        thinking_style_notes=[{"title": "Системный подход", "description": "..."}],
    )
    db_session.add(analysis)
    await db_session.flush()
    await db_session.refresh(analysis)

    assert analysis.report_version == 2
    assert len(analysis.strength_cards) == 1
    assert len(analysis.thinking_style_notes) == 1

    validated = AdminAnalysisResultResponse.model_validate(analysis)
    assert validated.report_version == 2
    assert validated.strength_cards[0].title == "Любишь докапываться до сути"
    assert validated.thinking_style_notes[0].title == "Системный подход"
