"""«Сильные стороны» in a generated report (PRO-432): built from the new
tests, stored with their grounding, safe under an LLM failure, and rebuilt by
the psychologist when the strength rules change."""
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import use_locale
from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment
from app.models.astur_run import AsturRun, AsturRunStatus
from app.models.belbin_run import BelbinRun
from app.models.user import User
from app.services import assessment_shared, llm_client
from app.services import student_strengths_service as strengths
from scripts.belbin_bank import ROLES
from tests.integration.astur_helpers import v1_version_id
from tests.integration.review_helpers import (
    assign,
    capture_emails,
    force_complete_senior,
    generate,
    make_student_assessment,
    stored_result,
)
from tests.strength_fixtures import astur_snapshot


def _result_url(student: User, assessment_id: uuid.UUID) -> str:
    return f"/api/v1/psychologist/students/{student.id}/results/{assessment_id}"


async def _seed_battery(db_session: AsyncSession, assessment: Assessment, student: User, *, leading_role: str) -> None:
    totals = {role: 6 for role in ROLES}
    totals[leading_role] = 28
    db_session.add(BelbinRun(
        assessment_id=assessment.id, user_id=student.id, allocations=[], role_totals=totals,
    ))
    db_session.add(AsturRun(
        assessment_id=assessment.id,
        user_id=student.id,
        bank_version_id=await v1_version_id(db_session),
        status=AsturRunStatus.completed,
        completed_at=datetime.now(timezone.utc),
        result_snapshot=astur_snapshot({"numeric_series": 90}).model_dump(mode="json"),
    ))
    await db_session.flush()


async def test_report_strength_cards_come_from_the_new_tests(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    assessment = await make_student_assessment(db_session, test_user)
    await _seed_battery(db_session, assessment, test_user, leading_role="finisher")

    await generate(client, auth_headers, assessment)

    stored = await stored_result(db_session, assessment.id)
    by_basis = {card["basis"]: card for card in stored.strength_cards}
    assert by_basis["task_result"]["title"] == "Ты хорошо замечаешь закономерности в числах"
    assert "доводишь работу до результата" in by_basis["self_report"]["title"]
    assert all("try_now" not in card for card in stored.strength_cards)
    assert stored.meta["strengths_rules_version"] == strengths.student_strengths_rules.version
    # Internal ids never reach stored (student-facing) text.
    assert not any(marker in json.dumps(stored.strength_cards) for marker in ("strength:", "belbin:", "astur:"))


async def test_llm_failure_falls_back_to_the_same_vetted_cards(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    monkeypatch.setattr(llm_client, "is_enabled", lambda: True)
    monkeypatch.setattr(llm_client, "complete_json", AsyncMock(side_effect=llm_client.LLMError("down")))
    assessment = await make_student_assessment(db_session, test_user)
    await _seed_battery(db_session, assessment, test_user, leading_role="plant")

    await generate(client, auth_headers, assessment)

    stored = await stored_result(db_session, assessment.id)
    with use_locale("ru"):
        expected = strengths.select_strengths(await strengths.collect_inputs(assessment.id, db_session))
    assert [card["title"] for card in stored.strength_cards] == [c.title for c in expected]
    assert [card["basis"] for card in stored.strength_cards] == [c.basis for c in expected]


async def test_published_report_from_an_older_rules_version_requires_rebuild(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    test_user: User,
    psychologist_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    assessment = await make_student_assessment(db_session, test_user)
    await _seed_battery(db_session, assessment, test_user, leading_role="finisher")
    await generate(client, auth_headers, assessment)
    await assign(db_session, psychologist_user, test_user)
    review_url = _result_url(test_user, assessment.id)
    assert (await client.post(f"{review_url}/publish", headers=psychologist_headers)).status_code == 200

    stored = await stored_result(db_session, assessment.id)
    stored.meta = {
        key: value for key, value in stored.meta.items()
        if key != "strengths_rules_version"
    }
    await db_session.flush()

    student_view = await client.get(f"/api/v1/result/{assessment.id}", headers=auth_headers)
    assert student_view.json() == {
        "status": "pending_review",
        "assessment_id": str(assessment.id),
    }
    queue = await client.get("/api/v1/psychologist/reviews", headers=psychologist_headers)
    assert queue.status_code == 200
    assert str(assessment.id) in {item["assessment_id"] for item in queue.json()}

    detail = await client.get(review_url, headers=psychologist_headers)
    assert detail.status_code == 200
    assert detail.json()["review_status"] == "published"
    assert detail.json()["strengths_stale"] is True

    rebuilt = await client.post(f"{review_url}/strengths/rebuild", headers=psychologist_headers)
    assert rebuilt.status_code == 200
    assert rebuilt.json()["review_status"] == "pending_review"
    assert rebuilt.json()["strengths_stale"] is False

    refreshed = await stored_result(db_session, assessment.id)
    assert refreshed.meta["strengths_rules_version"] == strengths.student_strengths_rules.version
    assert (await client.post(f"{review_url}/publish", headers=psychologist_headers)).status_code == 200


async def test_kk_translation_keeps_the_same_cards_and_their_grounding(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    assessment = await make_student_assessment(db_session, test_user)
    await _seed_battery(db_session, assessment, test_user, leading_role="finisher")
    await generate(client, auth_headers, assessment)
    ru_row = await stored_result(db_session, assessment.id)
    ru_cards = list(ru_row.strength_cards)
    ru_rules_version = ru_row.meta["strengths_rules_version"]

    def _kk_translation(*_args, **_kwargs) -> dict:
        return {
            "summary": "Қысқаша қорытынды.",
            "final_analysis": "Барлығын бірге қарастыр.",
            "strength_cards": [
                {"title": f"Күшті жақ {i}", "description": "Сипаттама мәтіні."}
                for i in range(len(ru_cards))
            ],
            "thinking_style_notes": [],
        }

    monkeypatch.setattr(llm_client, "is_enabled", lambda: True)
    monkeypatch.setattr(llm_client, "complete_json", AsyncMock(side_effect=_kk_translation))
    test_user.locale = "kk"
    await db_session.flush()
    await assessment_shared.get_redis().delete(*assessment_shared.report_cache_keys(assessment.id))

    await generate(client, auth_headers, assessment)

    kk_row = (
        await db_session.execute(
            select(AnalysisResult)
            .where(AnalysisResult.assessment_id == assessment.id, AnalysisResult.locale == "kk")
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert [c["basis"] for c in kk_row.strength_cards] == [c["basis"] for c in ru_cards]
    assert kk_row.strength_cards[0]["title"] == "Күшті жақ 0"
    assert "try_now" not in kk_row.strength_cards[0]
    assert kk_row.meta["strengths_rules_version"] == ru_rules_version
