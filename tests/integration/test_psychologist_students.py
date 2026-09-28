"""GET /api/v1/psychologist/students — assigned students only (PRO-327).
Detail + full report also covered here."""

import uuid
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.profile import AgeGroup, Profile
from app.models.user import User

from app.models.analysis_result import ReviewStatus
from tests.integration.review_helpers import (
    assign,
    capture_emails,
    force_complete_senior,
    generate,
    make_student_assessment,
    stored_result,
)


async def test_list_students_requires_psychologist(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.get("/api/v1/psychologist/students", headers=auth_headers)
    assert response.status_code == 403


async def test_list_students_rejects_admin(
    client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.get("/api/v1/psychologist/students", headers=admin_headers)
    assert response.status_code == 403


async def test_list_students_empty_without_assignments(
    client: httpx.AsyncClient, psychologist_headers: dict[str, str]
) -> None:
    response = await client.get(
        "/api/v1/psychologist/students", headers=psychologist_headers
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_list_and_get_assigned_student(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await assign(db_session, psychologist_user, test_user)

    listed = await client.get(
        "/api/v1/psychologist/students", headers=psychologist_headers
    )
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 1
    assert items[0]["id"] == str(test_user.id)
    assert items[0]["email"] == test_user.email

    detail = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}",
        headers=psychologist_headers,
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == str(test_user.id)
    assert body["email"] == test_user.email
    assert "is_admin" not in body
    assert "role" not in body
    assert "assessments" in body


async def test_get_unassigned_student_returns_404(
    client: httpx.AsyncClient,
    psychologist_headers: dict[str, str],
    test_user: User,
) -> None:
    response = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}",
        headers=psychologist_headers,
    )
    assert response.status_code == 404


async def test_get_unknown_student_returns_404(
    client: httpx.AsyncClient, psychologist_headers: dict[str, str]
) -> None:
    response = await client.get(
        f"/api/v1/psychologist/students/{uuid.uuid4()}",
        headers=psychologist_headers,
    )
    assert response.status_code == 404


async def test_get_student_test_results_requires_assignment(
    client: httpx.AsyncClient,
    psychologist_headers: dict[str, str],
    test_user: User,
) -> None:
    # No assignment created — must 404 before the assessment lookup even runs.
    response = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}/assessments/{uuid.uuid4()}/test-results",
        headers=psychologist_headers,
    )
    assert response.status_code == 404


async def test_get_student_test_results_unknown_assessment_404(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await assign(db_session, psychologist_user, test_user)

    response = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}/assessments/{uuid.uuid4()}/test-results",
        headers=psychologist_headers,
    )
    assert response.status_code == 404


async def test_available_students_flags_completed_assessment(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    test_user: User,
) -> None:
    """PRO-402: claim CTA needs has_completed_assessment, not only pending review."""
    before = await client.get(
        "/api/v1/psychologist/students/available", headers=psychologist_headers
    )
    assert before.status_code == 200
    row = next(item for item in before.json() if item["id"] == str(test_user.id))
    assert row["has_completed_assessment"] is False
    assert row["has_pending_review"] is False

    profile = Profile(
        user_id=test_user.id,
        name="Test Student",
        age=16,
        grade=10,
        city="Алматы",
        country="Казахстан",
        language="ru",
        age_group=AgeGroup.senior,
    )
    db_session.add(profile)
    await db_session.flush()
    completed_at = datetime(2026, 9, 20, 10, 30, tzinfo=timezone.utc)
    db_session.add(
        Assessment(
            profile_id=profile.id,
            goal=AssessmentGoal.explore,
            status=AssessmentStatus.completed,
            completed_at=completed_at,
        )
    )
    # A newer attempt still in progress must not replace the completed one.
    db_session.add(Assessment(profile_id=profile.id, goal=AssessmentGoal.university))
    await db_session.commit()

    after = await client.get(
        "/api/v1/psychologist/students/available", headers=psychologist_headers
    )
    assert after.status_code == 200
    row = next(item for item in after.json() if item["id"] == str(test_user.id))
    assert row["has_completed_assessment"] is True
    assert row["has_pending_review"] is False
    assert row["grade"] == 10
    assert row["goal"] == "explore"
    assert datetime.fromisoformat(row["completed_at"]) == completed_at


async def test_scope_available_excludes_already_claimed_student(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    """PRO-422: ?scope=available must not return students already claimed."""
    # Psychologists self-claim students; the link itself is what matters here.
    await assign(db_session, psychologist_user, test_user)

    mine = await client.get(
        "/api/v1/psychologist/students?scope=mine", headers=psychologist_headers
    )
    assert mine.status_code == 200
    assert any(item["id"] == str(test_user.id) for item in mine.json())

    for path in (
        "/api/v1/psychologist/students?scope=available",
        "/api/v1/psychologist/students/available",
    ):
        available = await client.get(path, headers=psychologist_headers)
        assert available.status_code == 200, path
        assert all(item["id"] != str(test_user.id) for item in available.json()), path


async def test_available_waiting_since_follows_the_pending_report(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Older assessment still pending, newer one already published: the pool
    shows how long the pending one has waited, not the newer one."""
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    older = await make_student_assessment(db_session, test_user)
    older.status, older.completed_at = AssessmentStatus.completed, datetime(2026, 9, 1, tzinfo=timezone.utc)
    newer = Assessment(
        profile_id=older.profile_id,
        goal=AssessmentGoal.university,
        status=AssessmentStatus.completed,
        completed_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
    )
    db_session.add(newer)
    await db_session.flush()
    await generate(client, auth_headers, older)
    await generate(client, auth_headers, newer)
    stored = await stored_result(db_session, newer.id)
    stored.review_status = ReviewStatus.published
    await db_session.flush()

    rows = (await client.get("/api/v1/psychologist/students/available", headers=psychologist_headers)).json()
    row = next(item for item in rows if item["id"] == str(test_user.id))
    assert row["has_pending_review"] is True
    assert row["goal"] == "explore"
    assert datetime.fromisoformat(row["completed_at"]) == datetime(2026, 9, 1, tzinfo=timezone.utc)

    # Both pending: the oldest one is how long the student has waited.
    stored.review_status = ReviewStatus.pending_review
    await db_session.flush()
    rows = (await client.get("/api/v1/psychologist/students/available", headers=psychologist_headers)).json()
    row = next(item for item in rows if item["id"] == str(test_user.id))
    assert datetime.fromisoformat(row["completed_at"]) == datetime(2026, 9, 1, tzinfo=timezone.utc)
