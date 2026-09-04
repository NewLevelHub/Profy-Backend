"""PRO-262 §5/§6: real activity, and the whole-table counts that depend on it.

The users list carried only `created_at`, shown under an "ACTIVITY" heading —
a registration date reading as "was here 2 days ago". With nothing recording
when a user was actually seen, "abandoned on the diagnostic: N" could not be
computed at all and the redesign dropped the tile
(docs/admin-backend-requests-pro-242.md §5, §6).
"""

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import ACTIVITY_REFRESH_INTERVAL
from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.product_feedback import ProductFeedback
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import admin_service, auth_service


@pytest_asyncio.fixture
async def admin_headers(db_session: AsyncSession) -> dict[str, str]:
    admin = User(
        email=f"{uuid.uuid4()}@admin.test",
        hashed_password="x",
        is_active=True,
        is_verified=True,
        is_admin=True,
    )
    db_session.add(admin)
    await db_session.flush()
    return {"Authorization": f"Bearer {auth_service.create_jwt_token(admin.id)}"}


async def _user(db: AsyncSession, *, marker: str = "", last_active_at=None) -> User:
    user = User(
        email=f"{uuid.uuid4()}-{marker}@example.test",
        hashed_password=auth_service.hash_password("Testpass123!"),
        is_active=True,
        is_verified=True,
        last_active_at=last_active_at,
    )
    db.add(user)
    await db.flush()
    return user


async def _assessment(db: AsyncSession, user: User, status: AssessmentStatus) -> Assessment:
    profile = Profile(
        user_id=user.id,
        name="Тест",
        age=16,
        grade=10,
        city="Алматы",
        country="Казахстан",
        language="ru",
        age_group=AgeGroup.senior,
    )
    db.add(profile)
    await db.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore, status=status)
    db.add(assessment)
    await db.flush()
    return assessment


# --- recording activity -----------------------------------------------------


async def test_an_authenticated_request_records_the_user_as_seen(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await _user(db_session)
    assert user.last_active_at is None
    headers = {"Authorization": f"Bearer {auth_service.create_jwt_token(user.id)}"}

    response = await client.get("/api/v1/profile", headers=headers)

    assert response.status_code in (200, 404)  # no profile yet is fine; auth ran either way
    await db_session.refresh(user)
    assert user.last_active_at is not None


async def test_a_fresh_timestamp_is_not_rewritten_on_every_request(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """Writing on each request would turn every read endpoint into a write and
    put an active session in contention for its own row; the screens this
    feeds are all day-scale."""
    recent = datetime.now(timezone.utc) - ACTIVITY_REFRESH_INTERVAL / 2
    user = await _user(db_session, last_active_at=recent)
    headers = {"Authorization": f"Bearer {auth_service.create_jwt_token(user.id)}"}

    await client.get("/api/v1/profile", headers=headers)

    await db_session.refresh(user)
    assert user.last_active_at == recent


async def test_a_stale_timestamp_is_refreshed(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    stale = datetime.now(timezone.utc) - ACTIVITY_REFRESH_INTERVAL * 3
    user = await _user(db_session, last_active_at=stale)
    headers = {"Authorization": f"Bearer {auth_service.create_jwt_token(user.id)}"}

    await client.get("/api/v1/profile", headers=headers)

    await db_session.refresh(user)
    assert user.last_active_at > stale


# --- using it ---------------------------------------------------------------


async def test_users_can_be_filtered_by_how_long_they_have_been_quiet(
    db_session: AsyncSession,
) -> None:
    """Never being seen is not the same as having gone quiet: `last_active_at`
    is null for everyone who has not been back since it started being
    recorded, so treating null as "inactive forever" would return an account
    registered five minutes ago from ?inactive_days=365. Registration is
    itself activity, and it is the floor."""
    marker = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    quiet = await _user(db_session, marker=marker, last_active_at=now - timedelta(days=30))
    fresh_never_seen = await _user(db_session, marker=marker)
    old_never_seen = await _user(db_session, marker=marker)
    old_never_seen.created_at = now - timedelta(days=30)
    await _user(db_session, marker=marker, last_active_at=now - timedelta(hours=1))
    await db_session.flush()

    result = await admin_service.list_users(
        db_session, search=marker, inactive_days=7, limit=100
    )

    assert {i.id for i in result.items} == {quiet.id, old_never_seen.id}
    assert fresh_never_seen.id not in {i.id for i in result.items}


async def test_users_list_exposes_and_sorts_by_last_active(db_session: AsyncSession) -> None:
    marker = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    older = await _user(db_session, marker=marker, last_active_at=now - timedelta(days=5))
    newer = await _user(db_session, marker=marker, last_active_at=now - timedelta(days=1))

    result = await admin_service.list_users(
        db_session, search=marker, sort="last_active_at", order="desc", limit=100
    )

    assert [i.id for i in result.items] == [newer.id, older.id]
    assert result.items[0].last_active_at is not None


async def test_user_stats_counts_abandoned_diagnostics(db_session: AsyncSession) -> None:
    """An assessment still in progress whose owner has not been seen for the
    threshold. This is the tile that could not exist before: it needs a slice
    of the whole table, not a page of twenty."""
    before = await admin_service.get_user_stats(db_session, inactive_days=7)

    now = datetime.now(timezone.utc)
    quiet = await _user(db_session, last_active_at=now - timedelta(days=30))
    await _assessment(db_session, quiet, AssessmentStatus.in_progress)

    still_here = await _user(db_session, last_active_at=now)
    await _assessment(db_session, still_here, AssessmentStatus.in_progress)

    finished = await _user(db_session, last_active_at=now - timedelta(days=30))
    await _assessment(db_session, finished, AssessmentStatus.completed)

    stats = await admin_service.get_user_stats(db_session, inactive_days=7)

    # Only the quiet user's unfinished assessment counts: the active user is
    # still working on theirs, and the third one is done, not abandoned.
    assert stats.abandoned_diagnostics == before.abandoned_diagnostics + 1
    assert stats.completed_diagnostics == before.completed_diagnostics + 1
    assert stats.total == before.total + 3
    assert stats.signups_last_7d == before.signups_last_7d + 3
    assert stats.inactive_days_threshold == 7


async def test_abandoned_count_follows_the_threshold(db_session: AsyncSession) -> None:
    baseline = await admin_service.get_user_stats(db_session, inactive_days=7)
    baseline_wide = await admin_service.get_user_stats(db_session, inactive_days=90)

    user = await _user(db_session, last_active_at=datetime.now(timezone.utc) - timedelta(days=30))
    await _assessment(db_session, user, AssessmentStatus.in_progress)

    strict = await admin_service.get_user_stats(db_session, inactive_days=7)
    lenient = await admin_service.get_user_stats(db_session, inactive_days=90)

    assert strict.abandoned_diagnostics == baseline.abandoned_diagnostics + 1
    assert lenient.abandoned_diagnostics == baseline_wide.abandoned_diagnostics


async def test_a_user_with_no_recorded_activity_is_judged_by_the_assessment_start(
    db_session: AsyncSession,
) -> None:
    """Accounts predating activity tracking must not be counted as active — a
    plain NULL comparison would silently exclude every one of them. They fall
    back to their registration date, the same rule the users list filters on,
    so the tile and the list below it cannot disagree."""
    baseline = await admin_service.get_user_stats(db_session, inactive_days=7)

    user = await _user(db_session)
    user.created_at = datetime.now(timezone.utc) - timedelta(days=30)
    await _assessment(db_session, user, AssessmentStatus.in_progress)
    await db_session.flush()

    stats = await admin_service.get_user_stats(db_session, inactive_days=7)
    listed = await admin_service.list_users(
        db_session, search=user.email, inactive_days=7, limit=10
    )

    assert stats.abandoned_diagnostics == baseline.abandoned_diagnostics + 1
    assert [i.id for i in listed.items] == [user.id]


async def test_users_stats_route_is_not_swallowed_by_the_detail_route(
    client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> None:
    """/users/stats has to be declared before /users/{user_id}, or "stats" is
    parsed as a user id."""
    response = await client.get("/api/v1/admin/users/stats", headers=admin_headers)

    assert response.status_code == 200
    assert "abandoned_diagnostics" in response.json()


# --- feedback histogram -----------------------------------------------------


async def test_feedback_stats_carry_the_full_score_histogram(
    db_session: AsyncSession,
) -> None:
    """The 1-5 histogram is the feedback screen's main chart, and an average
    cannot reconstruct it — two very different distributions share a mean."""
    marker = f"pro262-{uuid.uuid4()}"
    for score in (1, 1, 5):
        user = await _user(db_session)
        db_session.add(
            ProductFeedback(
                user_id=user.id, relevance_score=score, helpful_sections=[marker]
            )
        )
    await db_session.flush()

    stats = await admin_service.get_feedback_stats(db_session, section=marker)

    assert stats.score_counts == {"1": 2, "2": 0, "3": 0, "4": 0, "5": 1}
    assert stats.total == 3
