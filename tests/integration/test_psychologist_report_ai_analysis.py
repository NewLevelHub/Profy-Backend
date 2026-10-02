"""PRO-338+ — the psychologist report's `ai_analysis` field: lazily
generated + cached on first GET (product decision: auto-generate rather
than requiring an explicit action first), plus an explicit regenerate
endpoint that bypasses the cache. llm_client is mocked throughout — no real
network calls."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.psychoemotional_run import PsychoEmotionalRun, PsychoEmotionalValidityFlag
from app.models.user import User
from app.services import llm_client
from app.services.psychoemotional import engine as psychoemotional_engine

from tests.integration.review_helpers import assign


async def _make_assessment_for(db: AsyncSession, owner: User) -> Assessment:
    profile = Profile(
        user_id=owner.id, name="Аружан Абенова", age=16, grade=10, city="Алматы",
        country="Казахстан", language="ru", age_group=AgeGroup.senior,
    )
    db.add(profile)
    await db.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()
    return assessment


def _minimal_report_kwargs(assessment_id: uuid.UUID) -> dict:
    return dict(
        assessment_id=assessment_id,
        summary="Итоговое summary",
        profile={"R": 50.0, "I": 40.0, "A": 30.0, "S": 20.0, "E": 10.0, "C": 5.0},
        code=["R", "I", "A"],
        meta={"differentiation": 40.0, "consistency": "high", "aversion": {}},
        careers=[{
            "slug": "swe", "name": "Разработчик", "holland_code": "RI", "match_score": 0.9,
            "description": "", "professions": [], "skills_needed": [], "subjects_to_develop": [],
            "first_steps": ["Попробуй"],
        }],
        strengths=["R"],
        weaknesses=["C"],
        development_plan={"reinforce": [], "compensate": []},
        big_five={},
        thinking_style={"creative_think": 0.0, "systematic": 0.0, "strategic": 0.0, "practical": 0.0},
        personality_highlights=[],
        motivation={},
        motivation_top=[],
        motivation_highlights=["Тебе важно докапываться до сути"],
        personality_profile={
            "openness": 50.0, "conscientiousness": 50.0, "extraversion": 50.0,
            "agreeableness": 50.0, "emotional_stability": 50.0,
        },
        personality_notes={},
        report_version=2,
        strength_cards=[{"title": "Сильная сторона", "description": "..."}],
        thinking_style_notes=[{"title": "Стиль мышления", "description": "..."}],
    )


def _valid_raw() -> dict:
    # Must cover every block `_minimal_report_kwargs` produces: interest_map
    # (always present) + personality_notes (always present) + this fixture's
    # own non-empty thinking_style_notes + motivation_highlights.
    return {
        "block_analyses": [
            {"block": "interests", "text": "Комментарий по интересам."},
            {"block": "personality", "text": "Комментарий по личности."},
            {"block": "thinking_style", "text": "Комментарий по стилю мышления."},
            {"block": "motivation", "text": "Комментарий по мотивации."},
        ],
        "final_summary": "Раз. Два. Три. Четыре.",
        "recommended_profession": {"slug": "swe", "name": "Разработчик", "reasoning": "Обоснование."},
    }


async def test_ai_analysis_is_generated_and_cached_on_first_view(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await assign(db_session, psychologist_user, test_user)
    assessment = await _make_assessment_for(db_session, test_user)
    db_session.add(AnalysisResult(**_minimal_report_kwargs(assessment.id)))
    await db_session.flush()

    with (
        patch.object(llm_client, "is_enabled", return_value=True),
        patch.object(llm_client, "complete_json", new=AsyncMock(return_value=_valid_raw())) as mock_complete,
    ):
        first = await client.get(
            f"/api/v1/psychologist/students/{test_user.id}/assessments/{assessment.id}/report",
            headers=psychologist_headers,
        )
        assert first.status_code == 200
        ai_analysis = first.json()["ai_analysis"]
        assert ai_analysis is not None
        assert ai_analysis["recommended_profession"]["slug"] == "swe"
        assert mock_complete.call_count == 1

        # Second view must NOT call the LLM again — cached on AnalysisResult.
        second = await client.get(
            f"/api/v1/psychologist/students/{test_user.id}/assessments/{assessment.id}/report",
            headers=psychologist_headers,
        )
        assert second.status_code == 200
        assert second.json()["ai_analysis"] == ai_analysis
        assert mock_complete.call_count == 1

    analysis = (await db_session.execute(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment.id)
    )).scalar_one()
    assert analysis.psych_ai_analysis is not None


async def test_ai_analysis_is_generated_with_a_psychoemotional_block_and_history(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    """Regression: the МЦВ section carries datetimes (completed_at, and one per
    history item) — the prompt's json.dumps used to crash on them, so every
    student with this test got ai_analysis=None. Two scored runs, so the
    history path is covered too, not only the top-level field."""
    await assign(db_session, psychologist_user, test_user)
    assessment = await _make_assessment_for(db_session, test_user)
    db_session.add(AnalysisResult(**_minimal_report_kwargs(assessment.id)))
    for days_ago, (list1, list2) in (
        (30, ([3, 4, 2, 1, 5, 6, 0, 7], [3, 2, 4, 1, 5, 0, 6, 7])),
        (1, ([1, 2, 3, 4, 5, 6, 7, 0], [2, 1, 3, 4, 5, 6, 0, 7])),
    ):
        db_session.add(PsychoEmotionalRun(
            assessment_id=assessment.id, user_id=test_user.id, list1=list1, list2=list2,
            metrics=psychoemotional_engine.compute(list1, list2).as_dict(),
            validity_flag=PsychoEmotionalValidityFlag.ok,
            created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        ))
    await db_session.flush()

    raw = _valid_raw()
    raw["block_analyses"].append({"block": "psychoemotional", "text": "Комментарий по МЦВ."})
    with (
        patch.object(llm_client, "is_enabled", return_value=True),
        patch.object(llm_client, "complete_json", new=AsyncMock(return_value=raw)) as mock_complete,
    ):
        response = await client.get(
            f"/api/v1/psychologist/students/{test_user.id}/assessments/{assessment.id}/report",
            headers=psychologist_headers,
        )

    assert response.status_code == 200
    assert response.json()["ai_analysis"] is not None
    assert mock_complete.call_count == 1
    system_prompt = mock_complete.call_args.args[0][0]["content"]
    assert '"block": "psychoemotional"' in system_prompt
    assert '"history"' in system_prompt

    # PRO-448: the specialist gets the text interpretation of the latest run
    # (green first, black last → root conflict "27"); the AI prompt does not.
    interpretation = response.json()["report"]["psychoemotional"]["interpretation"]
    assert [p["sign"] for p in interpretation["positions"]] == ["plus", "cross", "equal", "minus", "plus_minus"]
    assert interpretation["positions"][-1]["colors"] == [2, 7]
    assert len(interpretation["indices"]) == 3
    assert '"interpretation"' not in system_prompt


async def test_ai_analysis_is_none_when_llm_disabled(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    """LLM disabled must never break the rest of the report — ai_analysis is
    just None. Explicitly patched (not relying on ambient .env config,
    since some local/dev environments DO have a real LLM_ENABLED=true +
    LLM_API_KEY for other features like the report narrative — this test
    must never depend on that or risk a real, billed API call)."""
    await assign(db_session, psychologist_user, test_user)
    assessment = await _make_assessment_for(db_session, test_user)
    db_session.add(AnalysisResult(**_minimal_report_kwargs(assessment.id)))
    await db_session.flush()

    with (
        patch.object(llm_client, "is_enabled", return_value=False),
        patch.object(llm_client, "complete_json", new=AsyncMock(side_effect=AssertionError("must not be called"))),
    ):
        response = await client.get(
            f"/api/v1/psychologist/students/{test_user.id}/assessments/{assessment.id}/report",
            headers=psychologist_headers,
        )
    assert response.status_code == 200
    assert response.json()["ai_analysis"] is None
    assert response.json()["report"]["assessment_id"] == str(assessment.id)


async def test_regenerate_endpoint_bypasses_the_cache(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await assign(db_session, psychologist_user, test_user)
    assessment = await _make_assessment_for(db_session, test_user)
    db_session.add(AnalysisResult(**_minimal_report_kwargs(assessment.id)))
    await db_session.flush()

    with (
        patch.object(llm_client, "is_enabled", return_value=True),
        patch.object(llm_client, "complete_json", new=AsyncMock(return_value=_valid_raw())) as mock_complete,
    ):
        await client.get(
            f"/api/v1/psychologist/students/{test_user.id}/assessments/{assessment.id}/report",
            headers=psychologist_headers,
        )
        assert mock_complete.call_count == 1

        regenerate = await client.post(
            f"/api/v1/psychologist/students/{test_user.id}/assessments/{assessment.id}/report/ai-analysis/regenerate",
            headers=psychologist_headers,
        )
        assert regenerate.status_code == 200
        assert regenerate.json()["recommended_profession"]["slug"] == "swe"
        assert mock_complete.call_count == 2  # bypassed the cache, called again


async def test_regenerate_for_unassigned_student_is_404(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    test_user: User,
) -> None:
    assessment = await _make_assessment_for(db_session, test_user)
    response = await client.post(
        f"/api/v1/psychologist/students/{test_user.id}/assessments/{assessment.id}/report/ai-analysis/regenerate",
        headers=psychologist_headers,
    )
    assert response.status_code == 404
