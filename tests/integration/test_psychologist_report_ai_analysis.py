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

from app.models.analysis_result import AnalysisResult, ReviewStatus
from app.models.analysis_result_review_edit import AnalysisResultReviewEdit, ReviewEditSource
from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.psychoemotional_run import PsychoEmotionalRun, PsychoEmotionalValidityFlag
from app.models.user import User
from app.services import llm_client, psychologist_service, report_service, student_strengths_service
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
        "recommended_profession": {
            "slug": "swe", "name": "Разработчик", "reasoning": "Обоснование.",
            "reasoning_kk": "Негіздеме.",
        },
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


# --- AI-recommended career on top by default ---------------------------------


def _career(slug: str, name: str, score: float) -> dict:
    return {
        "slug": slug, "name": name, "holland_code": "RI", "match_score": score,
        "description": "", "professions": [], "skills_needed": [], "subjects_to_develop": [],
        "first_steps": ["Попробуй"],
    }


# RIASEC order: swe, dsg, doc.
_THREE_CAREERS = [_career("swe", "Разработчик", 0.9), _career("dsg", "Дизайнер", 0.8), _career("doc", "Врач", 0.7)]


def _raw_picking(slug: str) -> dict:
    raw = _valid_raw()
    name = next(c["name"] for c in _THREE_CAREERS if c["slug"] == slug)
    raw["recommended_profession"] = {
        "slug": slug, "name": name, "reasoning": f"Обоснование: {name}.", "reasoning_kk": f"Негіздеме: {name}.",
    }
    return raw


async def _report_with_three_careers(db: AsyncSession, student: User, **overrides) -> Assessment:
    assessment = await _make_assessment_for(db, student)
    db.add(AnalysisResult(**{**_minimal_report_kwargs(assessment.id), "careers": _THREE_CAREERS, **overrides}))
    await db.flush()
    return assessment


async def _career_slugs(db: AsyncSession, assessment_id: uuid.UUID) -> list[str]:
    row = (
        await db.execute(
            select(AnalysisResult)
            .where(AnalysisResult.assessment_id == assessment_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    return [c["slug"] for c in row.careers]


def _report_url(student: User, assessment_id: uuid.UUID) -> str:
    return f"/api/v1/psychologist/students/{student.id}/assessments/{assessment_id}/report"


def _result_url(student: User, assessment_id: uuid.UUID) -> str:
    return f"/api/v1/psychologist/students/{student.id}/results/{assessment_id}"


async def test_ai_recommended_career_is_put_first(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await assign(db_session, psychologist_user, test_user)
    assessment = await _report_with_three_careers(db_session, test_user)

    with (
        patch.object(llm_client, "is_enabled", return_value=True),
        patch.object(llm_client, "complete_json", new=AsyncMock(return_value=_raw_picking("doc"))) as mock_complete,
    ):
        assert (await client.get(_report_url(test_user, assessment.id), headers=psychologist_headers)).status_code == 200
        assert await _career_slugs(db_session, assessment.id) == ["doc", "swe", "dsg"]

        # The reorder is not new input — the cached analysis stays valid.
        assert (await client.get(_report_url(test_user, assessment.id), headers=psychologist_headers)).status_code == 200
        assert mock_complete.call_count == 1

    detail = (await client.get(_result_url(test_user, assessment.id), headers=psychologist_headers)).json()
    assert [c["slug"] for c in detail["careers"]] == ["doc", "swe", "dsg"]
    assert detail["ai_recommended_slug"] == "doc"
    # A system default, not a review.
    assert detail["reviewed_by"] is None
    assert detail["review_status"] == "pending_review"

    edits = (await client.get(f"{_result_url(test_user, assessment.id)}/edits", headers=psychologist_headers)).json()
    assert len(edits) == 1
    assert edits[0]["source"] == "ai_recommendation"
    assert edits[0]["editor_id"] is None
    assert [c["slug"] for c in edits[0]["changed_fields"]["careers"]["old"]] == ["swe", "dsg", "doc"]


async def test_psychologist_careers_order_is_never_overridden(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await assign(db_session, psychologist_user, test_user)
    assessment = await _report_with_three_careers(db_session, test_user)
    own_order = [_THREE_CAREERS[1], _THREE_CAREERS[0], _THREE_CAREERS[2]]
    patched = await client.patch(
        _result_url(test_user, assessment.id), json={"careers": own_order}, headers=psychologist_headers
    )
    assert patched.status_code == 200

    with (
        patch.object(llm_client, "is_enabled", return_value=True),
        patch.object(llm_client, "complete_json", new=AsyncMock(return_value=_raw_picking("doc"))),
    ):
        assert (await client.get(_report_url(test_user, assessment.id), headers=psychologist_headers)).status_code == 200

    assert await _career_slugs(db_session, assessment.id) == ["dsg", "swe", "doc"]


async def test_a_new_ai_pick_restores_the_riasec_order_under_it(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await assign(db_session, psychologist_user, test_user)
    assessment = await _report_with_three_careers(db_session, test_user)
    regenerate_url = f"{_report_url(test_user, assessment.id)}/ai-analysis/regenerate"

    with patch.object(llm_client, "is_enabled", return_value=True):
        with patch.object(llm_client, "complete_json", new=AsyncMock(return_value=_raw_picking("doc"))):
            await client.get(_report_url(test_user, assessment.id), headers=psychologist_headers)
        assert await _career_slugs(db_session, assessment.id) == ["doc", "swe", "dsg"]

        with patch.object(llm_client, "complete_json", new=AsyncMock(return_value=_raw_picking("dsg"))):
            assert (await client.post(regenerate_url, headers=psychologist_headers)).status_code == 200
        assert await _career_slugs(db_session, assessment.id) == ["dsg", "swe", "doc"]

        with patch.object(llm_client, "complete_json", new=AsyncMock(return_value=_raw_picking("swe"))):
            assert (await client.post(regenerate_url, headers=psychologist_headers)).status_code == 200
        assert await _career_slugs(db_session, assessment.id) == ["swe", "dsg", "doc"]


async def test_published_report_careers_are_not_reordered(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await assign(db_session, psychologist_user, test_user)
    assessment = await _report_with_three_careers(db_session, test_user, review_status=ReviewStatus.published)

    with (
        patch.object(llm_client, "is_enabled", return_value=True),
        patch.object(llm_client, "complete_json", new=AsyncMock(return_value=_raw_picking("doc"))),
    ):
        assert (await client.get(_report_url(test_user, assessment.id), headers=psychologist_headers)).status_code == 200

    assert await _career_slugs(db_session, assessment.id) == ["swe", "dsg", "doc"]
    edits = (await client.get(f"{_result_url(test_user, assessment.id)}/edits", headers=psychologist_headers)).json()
    assert edits == []


async def test_promotion_follows_the_stored_analysis(
    db_session: AsyncSession,
    psychologist_user: User,
    test_user: User,
) -> None:
    """With two generations in flight, the analysis stored last decides —
    the promotion reads the pick from the row, not from its caller."""
    await assign(db_session, psychologist_user, test_user)
    assessment = await _report_with_three_careers(db_session, test_user, psych_ai_analysis=_raw_picking("dsg"))
    row = (
        await db_session.execute(select(AnalysisResult).where(AnalysisResult.assessment_id == assessment.id))
    ).scalar_one()

    await psychologist_service._apply_ai_recommendation(db_session, row, student_id=test_user.id)

    assert await _career_slugs(db_session, assessment.id) == ["dsg", "swe", "doc"]


async def test_failed_promotion_never_breaks_the_report(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await assign(db_session, psychologist_user, test_user)
    assessment = await _report_with_three_careers(db_session, test_user)
    # The app's rollback expires every object of the shared test session.
    assessment_id, url = assessment.id, _report_url(test_user, assessment.id)

    with (
        patch.object(llm_client, "is_enabled", return_value=True),
        patch.object(llm_client, "complete_json", new=AsyncMock(return_value=_raw_picking("doc"))),
        patch.object(
            psychologist_service.report_service, "lock_report_generation",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
    ):
        response = await client.get(url, headers=psychologist_headers)

    assert response.status_code == 200
    assert response.json()["ai_analysis"]["recommended_profession"]["slug"] == "doc"
    assert await _career_slugs(db_session, assessment_id) == ["swe", "dsg", "doc"]


async def test_regeneration_shows_the_model_the_riasec_order(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    """After a promotion the stored order starts with the previous pick; the
    model must still read the careers in the system's order."""
    await assign(db_session, psychologist_user, test_user)
    assessment = await _report_with_three_careers(db_session, test_user)

    with patch.object(llm_client, "is_enabled", return_value=True):
        with patch.object(llm_client, "complete_json", new=AsyncMock(return_value=_raw_picking("doc"))):
            await client.get(_report_url(test_user, assessment.id), headers=psychologist_headers)
        assert await _career_slugs(db_session, assessment.id) == ["doc", "swe", "dsg"]

        with patch.object(llm_client, "complete_json", new=AsyncMock(return_value=_raw_picking("doc"))) as mock_complete:
            await client.post(
                f"{_report_url(test_user, assessment.id)}/ai-analysis/regenerate", headers=psychologist_headers
            )

    system_prompt = mock_complete.call_args.args[0][0]["content"]
    positions = [system_prompt.index(f'"slug": "{slug}"') for slug in ("swe", "dsg", "doc")]
    assert positions == sorted(positions)


async def test_report_with_two_locale_rows_reads_the_row_under_review(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    """A kk-first report later translated to ru has two rows. The specialist
    report used to expect exactly one and 500'd; it reads the row under
    review (ru) — the same one the editor and publishing work on — and the
    AI pick reorders both rows, logged on the ru one."""
    await assign(db_session, psychologist_user, test_user)
    assessment = await _make_assessment_for(db_session, test_user)
    kk_careers = [{**c, "name": f"{c['name']} (kk)"} for c in _THREE_CAREERS]
    db_session.add(AnalysisResult(**{
        **_minimal_report_kwargs(assessment.id), "locale": "kk", "summary": "kk summary", "careers": kk_careers,
    }))
    await db_session.flush()
    db_session.add(AnalysisResult(**{
        **_minimal_report_kwargs(assessment.id), "summary": "ru summary", "careers": _THREE_CAREERS,
    }))
    await db_session.flush()

    with (
        patch.object(llm_client, "is_enabled", return_value=True),
        patch.object(llm_client, "complete_json", new=AsyncMock(return_value=_raw_picking("doc"))),
    ):
        report = await client.get(_report_url(test_user, assessment.id), headers=psychologist_headers)
        regenerate = await client.post(
            f"{_report_url(test_user, assessment.id)}/ai-analysis/regenerate", headers=psychologist_headers
        )
    test_results = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}/assessments/{assessment.id}/test-results",
        headers=psychologist_headers,
    )

    assert report.status_code == 200
    assert report.json()["report"]["summary"] == "ru summary"
    assert regenerate.status_code == 200
    assert test_results.status_code == 200
    rows = {
        row.locale: row
        for row in (
            await db_session.execute(
                select(AnalysisResult)
                .where(AnalysisResult.assessment_id == assessment.id)
                .execution_options(populate_existing=True)
            )
        ).scalars().all()
    }
    assert rows["ru"].psych_ai_analysis is not None and rows["kk"].psych_ai_analysis is None
    assert [c["slug"] for c in rows["ru"].careers] == ["doc", "swe", "dsg"]
    assert [c["slug"] for c in rows["kk"].careers] == ["doc", "swe", "dsg"]
    assert rows["kk"].careers[0]["name"] == "Врач (kk)"
    # Each locale row gets the student text in its own language.
    assert rows["ru"].top_career_why == {"slug": "doc", "text": "Обоснование: Врач."}
    assert rows["kk"].top_career_why == {"slug": "doc", "text": "Негіздеме: Врач."}
    edits = (
        await db_session.execute(
            select(AnalysisResultReviewEdit).join(
                AnalysisResult, AnalysisResult.id == AnalysisResultReviewEdit.analysis_result_id
            ).where(AnalysisResult.assessment_id == assessment.id)
        )
    ).scalars().all()
    assert [(edit.analysis_result_id, edit.source) for edit in edits] == [
        (rows["ru"].id, ReviewEditSource.ai_recommendation)
    ]


# --- «Почему тебе подходит» of the best match from the AI analysis -----------


async def test_student_reads_the_ai_text_under_the_best_match(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await assign(db_session, psychologist_user, test_user)
    # A fresh strengths marker: the student gate treats an outdated one as under review.
    meta = student_strengths_service.mark_fresh({"differentiation": 40.0, "consistency": "high", "aversion": {}})
    assessment = await _report_with_three_careers(db_session, test_user, meta=meta)

    with (
        patch.object(llm_client, "is_enabled", return_value=True),
        patch.object(llm_client, "complete_json", new=AsyncMock(return_value=_raw_picking("doc"))) as mock_complete,
    ):
        psych_report = await client.get(_report_url(test_user, assessment.id), headers=psychologist_headers)
        # The AI's own input keeps the career-fit text: no regeneration loop.
        await client.get(_report_url(test_user, assessment.id), headers=psychologist_headers)
        assert mock_complete.call_count == 1
    assert psych_report.json()["report"]["careers"][0]["why_by_ai"] is False

    detail = (await client.get(_result_url(test_user, assessment.id), headers=psychologist_headers)).json()
    assert (detail["top_career_why"], detail["top_career_why_slug"]) == ("Обоснование: Врач.", "doc")

    published = await client.post(f"{_result_url(test_user, assessment.id)}/publish", headers=psychologist_headers)
    assert published.status_code == 200
    student_view = await client.get(f"/api/v1/result/{assessment.id}", headers=auth_headers)
    assert student_view.status_code == 200, student_view.text
    careers = student_view.json()["careers"]
    assert (careers[0]["slug"], careers[0]["why"], careers[0]["why_by_ai"]) == ("doc", "Обоснование: Врач.", True)
    assert [career["why_by_ai"] for career in careers[1:]] == [False, False]


async def test_ai_text_shows_only_while_its_career_is_first(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """The psychologist moved another career to the top — the AI text is
    about "doc", so the best match keeps its career-fit text."""
    assessment = await _report_with_three_careers(
        db_session, test_user, top_career_why={"slug": "doc", "text": "Обоснование: Врач."}
    )
    row = (
        await db_session.execute(select(AnalysisResult).where(AnalysisResult.assessment_id == assessment.id))
    ).scalar_one()

    careers = report_service._shape_response(row, locale="ru").careers

    assert careers[0].slug == "swe"
    assert [career.why_by_ai for career in careers] == [False, False, False]
    assert "Обоснование" not in careers[0].why


async def test_psychologist_text_is_kept_until_the_pick_changes(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await assign(db_session, psychologist_user, test_user)
    assessment = await _report_with_three_careers(db_session, test_user)
    regenerate_url = f"{_report_url(test_user, assessment.id)}/ai-analysis/regenerate"

    with patch.object(llm_client, "is_enabled", return_value=True):
        with patch.object(llm_client, "complete_json", new=AsyncMock(return_value=_raw_picking("doc"))):
            await client.get(_report_url(test_user, assessment.id), headers=psychologist_headers)
            patched = await client.patch(
                _result_url(test_user, assessment.id), json={"top_career_why": "Текст психолога."},
                headers=psychologist_headers,
            )
            assert patched.status_code == 200
            assert patched.json()["top_career_why"] == "Текст психолога."
            await client.post(regenerate_url, headers=psychologist_headers)
        detail = (await client.get(_result_url(test_user, assessment.id), headers=psychologist_headers)).json()
        assert detail["top_career_why"] == "Текст психолога."

        with patch.object(llm_client, "complete_json", new=AsyncMock(return_value=_raw_picking("dsg"))):
            await client.post(regenerate_url, headers=psychologist_headers)
        detail = (await client.get(_result_url(test_user, assessment.id), headers=psychologist_headers)).json()
        assert (detail["top_career_why"], detail["top_career_why_slug"]) == ("Обоснование: Дизайнер.", "dsg")

    edits = (await client.get(f"{_result_url(test_user, assessment.id)}/edits", headers=psychologist_headers)).json()
    text_edits = [edit for edit in edits if "top_career_why" in edit["changed_fields"]]
    assert [(edit["source"], edit["changed_fields"]["top_career_why"]) for edit in text_edits] == [
        ("psychologist", {"old": "Обоснование: Врач.", "new": "Текст психолога."})
    ]


async def test_patching_the_text_before_the_analysis_exists_is_rejected(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await assign(db_session, psychologist_user, test_user)
    assessment = await _report_with_three_careers(db_session, test_user)

    patched = await client.patch(
        _result_url(test_user, assessment.id), json={"top_career_why": "Текст."}, headers=psychologist_headers
    )

    assert patched.status_code == 422


def test_a_new_locale_row_takes_the_text_in_its_language() -> None:
    sibling = AnalysisResult(
        locale="ru",
        top_career_why={"slug": "doc", "text": "Обоснование: Врач."},
        psych_ai_analysis=_raw_picking("doc"),
    )

    assert report_service._carried_top_career_why(sibling, "kk", edited=False) == {
        "slug": "doc", "text": "Негіздеме: Врач.",
    }
    # The psychologist's wording has nothing to be translated with.
    assert report_service._carried_top_career_why(sibling, "kk", edited=True) == {
        "slug": "doc", "text": "Обоснование: Врач.",
    }
    assert report_service._carried_top_career_why(AnalysisResult(locale="ru"), "kk", edited=False) is None
