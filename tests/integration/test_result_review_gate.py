"""Student-facing side of the psychologist review gate (PRO-337,
docs/psychologist-review-gate-plan.md §2/§6): a new report stays hidden
behind a `pending_review` envelope and out of the cache until published."""

import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.models.analysis_result import AnalysisResult, ReviewStatus
from app.models.assessment import AssessmentGoal
from app.models.user import User
from app.services import assessment_shared, email_service

from tests.integration.review_helpers import (
    STUDENT_NAME,
    assign,
    capture_emails,
    force_complete_senior,
    generate,
    make_other_student,
    make_student_assessment,
    stored_result,
)


async def test_new_report_is_pending_and_never_cached(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    assessment = await make_student_assessment(db_session, test_user)
    envelope = {"status": "pending_review", "assessment_id": str(assessment.id)}

    generated = await generate(client, auth_headers, assessment)
    assert generated.status_code == 200
    assert generated.json() == envelope
    assert (await stored_result(db_session, assessment.id)).review_status == ReviewStatus.pending_review

    fetched = await client.get(f"/api/v1/result/{assessment.id}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json() == envelope

    # Repeated generate is idempotent and still gated.
    regenerated = await generate(client, auth_headers, assessment)
    assert regenerated.json() == envelope

    redis = assessment_shared.get_redis()
    assert await redis.get(assessment_shared.report_cache_key(assessment.id)) is None


async def test_published_report_is_returned_in_full_and_cached(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    assessment = await make_student_assessment(db_session, test_user)
    await generate(client, auth_headers, assessment)

    stored = await stored_result(db_session, assessment.id)
    stored.review_status = ReviewStatus.published
    await db_session.flush()

    redis = assessment_shared.get_redis()
    cache_key = assessment_shared.report_cache_key(assessment.id)
    try:
        fetched = await client.get(f"/api/v1/result/{assessment.id}", headers=auth_headers)
        assert fetched.status_code == 200
        body = fetched.json()
        assert "status" not in body
        assert body["interest_instrument"] == "riasec"
        assert body["summary"] == stored.summary
        assert await redis.get(cache_key) is not None

        regenerated = await generate(client, auth_headers, assessment)
        assert regenerated.json()["interest_instrument"] == "riasec"
    finally:
        await redis.delete(cache_key)


async def test_get_without_report_is_404(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    test_user: User,
) -> None:
    assessment = await make_student_assessment(db_session, test_user)
    response = await client.get(f"/api/v1/result/{assessment.id}", headers=auth_headers)
    assert response.status_code == 404


async def test_foreign_assessment_is_still_403_not_pending(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The frontend resets the session on 403 — the gate must not change
    what an ownership failure looks like."""
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    other = await make_other_student(db_session)
    assessment = await make_student_assessment(db_session, other)
    from app.services import auth_service

    other_headers = {"Authorization": f"Bearer {auth_service.create_jwt_token(other.id)}"}
    await generate(client, other_headers, assessment)

    response = await client.get(f"/api/v1/result/{assessment.id}", headers=auth_headers)
    assert response.status_code == 403


async def test_generation_emails_assigned_psychologist_once(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    test_user: User,
    psychologist_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emails = capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    assessment = await make_student_assessment(db_session, test_user)
    await assign(client, admin_headers, psychologist_user, test_user)

    await generate(client, auth_headers, assessment)
    await generate(client, auth_headers, assessment)

    emails["pending"].assert_awaited_once_with(psychologist_user.email, STUDENT_NAME)


async def test_notification_failure_does_not_break_generation(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    test_user: User,
    psychologist_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    force_complete_senior(monkeypatch)

    async def _explode(*_a, **_kw):
        raise RuntimeError("mail provider down")

    monkeypatch.setattr(email_service, "send_review_pending_email", _explode)
    assessment = await make_student_assessment(db_session, test_user)
    assessment_id = str(assessment.id)
    await assign(client, admin_headers, psychologist_user, test_user)

    response = await generate(client, auth_headers, assessment)
    assert response.status_code == 200
    assert response.json() == {"status": "pending_review", "assessment_id": assessment_id}
    assert (await stored_result(db_session, assessment.id)).review_status == ReviewStatus.pending_review


async def test_goal_context_does_not_generate_a_report_behind_the_gate(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """goal-context builds the report itself when there is none — without its
    own gate that is a way to generate one and read its content straight
    away, review or no review."""
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    assessment = await make_student_assessment(db_session, test_user)

    response = await client.get(
        f"/api/v1/result/{assessment.id}/goal-context", headers=auth_headers
    )
    assert response.status_code == 409

    # It may generate the report on the way (that is pre-existing behaviour,
    # and the psychologist queue picks it up) — what must not happen is
    # serving content derived from it.
    stored = (
        await db_session.execute(
            select(AnalysisResult).where(AnalysisResult.assessment_id == assessment.id)
        )
    ).scalar_one_or_none()
    assert stored is None or stored.review_status == ReviewStatus.pending_review


async def test_unknown_assessment_is_404(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.get(f"/api/v1/result/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


async def test_report_derived_endpoints_are_gated_until_published(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The envelope alone isn't the gate: goal overlay, roadmaps and gap
    analysis are all built from the same stored AnalysisResult, and would
    otherwise hand the student its content (top spheres, matched directions,
    a generated plan) before the psychologist published anything."""
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    assessment = await make_student_assessment(db_session, test_user)
    await generate(client, auth_headers, assessment)

    goal_context = await client.get(
        f"/api/v1/result/{assessment.id}/goal-context", headers=auth_headers
    )
    assert goal_context.status_code == 409

    generated_roadmap = await client.post(
        "/api/v1/roadmap/generate",
        json={"assessment_id": str(assessment.id)},
        headers=auth_headers,
    )
    assert generated_roadmap.status_code == 409

    fetched_roadmap = await client.get(
        f"/api/v1/roadmap/{assessment.id}", headers=auth_headers
    )
    assert fetched_roadmap.status_code == 409

    # The inquiry questions are LLM-generated from the same stored careers/
    # strengths, and its "unknown direction" 400 is an oracle over them.
    inquiry = await client.get(
        f"/api/v1/inquiry/{assessment.id}/directions/developer/questions",
        headers=auth_headers,
    )
    assert inquiry.status_code == 409

    stored = await stored_result(db_session, assessment.id)
    stored.review_status = ReviewStatus.published
    await db_session.flush()

    # Only the gate is asserted here — whatever these endpoints answer after
    # publication is their own contract, tested elsewhere.
    reopened = await client.get(
        f"/api/v1/result/{assessment.id}/goal-context", headers=auth_headers
    )
    assert reopened.status_code != 409


async def test_goal_choice_interstitial_works_while_report_is_pending(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Choosing a goal needs no report — the unsure-goal answer must not be
    blocked by the review gate while a report waits for the psychologist."""
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    assessment = await make_student_assessment(db_session, test_user)
    await generate(client, auth_headers, assessment)
    assessment.goal = AssessmentGoal.unsure
    await db_session.flush()

    response = await client.get(
        f"/api/v1/result/{assessment.id}/goal-context", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["needs_goal_selection"] is True
