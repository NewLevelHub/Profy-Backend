"""Admin filters must describe the values visible in each user row."""
import csv
import io
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.profile import AgeGroup, Profile
from app.models.user import User, UserRole
from app.services import admin_service


async def history(db, marker, name, attempts, *, tied=False):
    user = User(email=f"{name}-{marker}@example.test", hashed_password="x", is_verified=True)
    db.add(user)
    await db.flush()
    profile = Profile(user_id=user.id, name=name, age=16, grade=10, city="Test",
                      country="Test", language="ru", age_group=AgeGroup.senior)
    db.add(profile)
    await db.flush()
    start = datetime.now(timezone.utc) - timedelta(days=3)
    ids = sorted(uuid.uuid4() for _ in attempts)
    for index, (status, goal) in enumerate(attempts):
        db.add(Assessment(id=ids[index], profile_id=profile.id, status=status, goal=goal,
                          created_at=start if tied else start + timedelta(hours=index)))
    await db.flush()
    return user


@pytest.mark.parametrize("filters,expected", [
    ({"status": "completed"}, {"finished", "explore"}),
    ({"status": "in_progress"}, {"restarted"}),
    ({"goal": "university"}, {"finished"}),
    ({"goal": "profession"}, {"restarted"}),
    ({"goal": "explore"}, {"explore"}),
    ({"status": "completed", "goal": "university"}, {"finished"}),
    ({"status": "in_progress", "goal": "university"}, set()),
])
async def test_latest_filters_match_rows_pages_counts_and_csv(
    db_session: AsyncSession, client: httpx.AsyncClient, admin_headers, filters, expected,
):
    marker = uuid.uuid4().hex
    users = {}
    for name, attempts in {
        "restarted": [("completed", "university"), ("in_progress", "profession")],
        "finished": [("in_progress", "explore"), ("completed", "university")],
        "explore": [("completed", "university"), ("completed", "explore")],
        "empty": [],
    }.items():
        users[name] = await history(db_session, marker, name, attempts)

    params = {"search": marker, **filters, "sort": "email", "order": "asc", "limit": 1}
    seen = []
    for page in range(1, max(len(expected), 1) + 1):
        response = await client.get("/api/v1/admin/users", params={**params, "page": page}, headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == len(expected)
        for item in data["items"]:
            for key, value in filters.items():
                assert item[f"latest_assessment_{key}"] == value
            seen.append(item["id"])
    assert len(seen) == len(set(seen))
    assert set(seen) == {str(users[name].id) for name in expected}

    response = await client.get("/api/v1/admin/users/export", params={"search": marker, **filters}, headers=admin_headers)
    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(rows) == len(expected) + 1  # header + exactly the filtered users
    for name, user in users.items():
        assert (user.email in response.text) == (name in expected)


async def test_latest_ties_use_same_attempt_for_filter_and_display(db_session: AsyncSession):
    marker = uuid.uuid4().hex
    user = await history(db_session, marker, "tied", [
        ("completed", "university"), ("in_progress", "profession"),
    ], tied=True)
    matching = await admin_service.list_users(
        db_session, search=marker, status=AssessmentStatus.in_progress, goal=AssessmentGoal.profession,
    )
    assert [item.id for item in matching.items] == [user.id]
    assert matching.items[0].latest_assessment_status == "in_progress"
    assert matching.items[0].latest_assessment_goal == "profession"
    old = await admin_service.list_users(db_session, search=marker, status=AssessmentStatus.completed)
    assert old.total == 0


@pytest.mark.parametrize("role", list(UserRole))
@pytest.mark.parametrize("days", [7, 30, 90])
async def test_inactivity_uses_last_activity_for_every_role(db_session: AsyncSession, role, days):
    marker = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    quiet = []
    for name, created, active in [
        ("active_old_account", now - timedelta(days=120), now),
        ("quiet", now - timedelta(days=120), now - timedelta(days=days, hours=1)),
        ("just_under", now - timedelta(days=120), now - timedelta(days=days) + timedelta(hours=1)),
        ("old_untracked", now - timedelta(days=120), None),
        ("new_untracked", now, None),
    ]:
        user = User(email=f"{name}-{marker}@example.test", hashed_password="x", role=role,
                    created_at=created, last_active_at=active)
        db_session.add(user)
        quiet.extend([user] if name in ("quiet", "old_untracked") else [])
    await db_session.flush()
    filters = {"search": marker, "role": role, "inactive_days": days}
    result = await admin_service.list_users(db_session, **filters)
    exported = await admin_service.export_users(db_session, **filters)
    assert result.total == 2
    assert {item.id for item in result.items} == {user.id for user in quiet}
    assert {item.id for item in exported} == {user.id for user in quiet}
