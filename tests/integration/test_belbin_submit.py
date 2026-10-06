"""Belbin final submission and server-side block progress (PROFY-012).

The final POST still validates seven 8-value blocks and aggregates all role
totals; progress endpoints persist only individually completed blocks.
"""
import uuid
from unittest.mock import AsyncMock

from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.belbin_progress import BelbinProgress
from app.models.belbin_run import BelbinRun
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import assessment_shared, auth_service
from scripts.belbin_bank import SECTIONS


def _even_block(section: dict, *, first_item_points: int = 0) -> dict[str, int]:
    """A valid 10-point split across a section's 8 items — concentrates
    points on the first item plus spreads the rest, not a realistic answer,
    just something that sums to exactly 10."""
    ids = [item["id"] for item in section["items"]]
    allocation = {i: 0 for i in ids}
    allocation[ids[0]] = first_item_points
    remaining = 10 - first_item_points
    base, rem = divmod(remaining, 7)
    for i, item_id in enumerate(ids[1:]):
        allocation[item_id] = base + (1 if i < rem else 0)
    return allocation


_VALID_ALLOCATIONS = [_even_block(section, first_item_points=3) for section in SECTIONS]


async def _auth(db: AsyncSession) -> tuple[User, Assessment, dict]:
    user = User(
        email=f"{uuid.uuid4()}@example.com", hashed_password="x",
        is_active=True, is_verified=True,
    )
    db.add(user)
    await db.flush()
    profile = Profile(
        user_id=user.id, name="Т", age=16, grade=10, city="Алматы",
        country="Казахстан", language="ru", age_group=AgeGroup.senior,
    )
    db.add(profile)
    await db.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()
    headers = {"Authorization": f"Bearer {auth_service.create_jwt_token(user)}"}
    return user, assessment, headers


async def test_valid_submission_stores_a_run_with_role_totals(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/belbin",
        json={"allocations": _VALID_ALLOCATIONS}, headers=headers,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert sum(body["role_totals"].values()) == 70
    assert set(body["role_totals"].keys()) == {
        "implementer", "coordinator", "shaper", "plant",
        "resource_investigator", "evaluator", "team_worker", "finisher",
    }

    run = (await db_session.execute(
        select(BelbinRun).where(BelbinRun.id == uuid.UUID(body["run_id"]))
    )).scalar_one()
    assert run.assessment_id == assessment.id
    assert run.allocations == _VALID_ALLOCATIONS
    assert run.role_totals == body["role_totals"]


async def test_belbin_finalizes_assessment_when_it_is_the_last_required_stage(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completion is a backend invariant, not a consequence of UI order."""
    _, assessment, headers = await _auth(db_session)
    monkeypatch.setattr(
        assessment_shared,
        "likert_answered_count",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        assessment_shared,
        "likert_total_questions",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        assessment_shared,
        "motivation_completed",
        AsyncMock(return_value=True),
    )
    # Models the state in which ASTUR was completed before Belbin through a
    # stale tab or direct API client. Once this POST stores Belbin, the whole
    # required battery is complete.
    monkeypatch.setattr(
        assessment_shared,
        "belbin_and_astur_completed",
        AsyncMock(return_value=True),
    )

    response = await client.post(
        f"/api/v1/assessment/{assessment.id}/belbin",
        json={"allocations": _VALID_ALLOCATIONS},
        headers=headers,
    )

    assert response.status_code == 201, response.text
    await db_session.refresh(assessment)
    assert assessment.status == AssessmentStatus.completed
    assert assessment.completed_at is not None


async def test_completed_blocks_are_restored_overwritten_and_deleted_on_submit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)
    progress_url = f"/api/v1/assessment/{assessment.id}/belbin/progress"

    empty = await client.get(progress_url, headers=headers)
    assert empty.status_code == 200
    assert empty.json() == {"completed": False, "blocks": []}

    first = await client.put(
        f"{progress_url}/0",
        json={"allocation": _VALID_ALLOCATIONS[0]},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    assert first.json()["blocks"] == [
        {"block_index": 0, "allocation": _VALID_ALLOCATIONS[0]}
    ]

    replacement = _even_block(SECTIONS[0], first_item_points=4)
    overwritten = await client.put(
        f"{progress_url}/0",
        json={"allocation": replacement},
        headers=headers,
    )
    assert overwritten.status_code == 200, overwritten.text

    third = await client.put(
        f"{progress_url}/2",
        json={"allocation": _VALID_ALLOCATIONS[2]},
        headers=headers,
    )
    assert third.status_code == 200, third.text
    restored = await client.get(progress_url, headers=headers)
    assert restored.json()["blocks"] == [
        {"block_index": 0, "allocation": replacement},
        {"block_index": 2, "allocation": _VALID_ALLOCATIONS[2]},
    ]

    stored = await db_session.get(BelbinProgress, assessment.id)
    assert stored is not None
    assert stored.blocks == {
        "0": replacement,
        "2": _VALID_ALLOCATIONS[2],
    }

    submitted = await client.post(
        f"/api/v1/assessment/{assessment.id}/belbin",
        json={"allocations": _VALID_ALLOCATIONS},
        headers=headers,
    )
    assert submitted.status_code == 201, submitted.text
    assert (await client.get(progress_url, headers=headers)).json() == {
        "completed": True,
        "blocks": [],
    }
    assert (
        await db_session.execute(
            select(BelbinProgress).where(
                BelbinProgress.assessment_id == assessment.id
            )
        )
    ).scalar_one_or_none() is None

    late_save = await client.put(
        f"{progress_url}/0",
        json={"allocation": _VALID_ALLOCATIONS[0]},
        headers=headers,
    )
    assert late_save.status_code == 409


async def test_progress_rejects_invalid_block_or_allocation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)
    progress_url = f"/api/v1/assessment/{assessment.id}/belbin/progress"

    missing_block = await client.put(
        f"{progress_url}/7",
        json={"allocation": _VALID_ALLOCATIONS[0]},
        headers=headers,
    )
    assert missing_block.status_code == 422

    invalid = dict(_VALID_ALLOCATIONS[0])
    invalid[next(iter(invalid))] += 1
    wrong_total = await client.put(
        f"{progress_url}/0",
        json={"allocation": invalid},
        headers=headers,
    )
    assert wrong_total.status_code == 422
    assert await db_session.get(BelbinProgress, assessment.id) is None


async def test_block_not_summing_to_10_is_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)
    bad_allocations = [dict(a) for a in _VALID_ALLOCATIONS]
    first_id = next(iter(bad_allocations[0]))
    bad_allocations[0][first_id] += 1  # now sums to 11, not 10

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/belbin",
        json={"allocations": bad_allocations}, headers=headers,
    )

    assert resp.status_code == 422, resp.text


async def test_wrong_item_set_in_a_block_is_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)
    bad_allocations = [dict(a) for a in _VALID_ALLOCATIONS]
    real_id = next(iter(bad_allocations[0]))
    bad_allocations[0]["not_a_real_item"] = bad_allocations[0].pop(real_id)

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/belbin",
        json={"allocations": bad_allocations}, headers=headers,
    )

    assert resp.status_code == 422, resp.text


async def test_wrong_number_of_blocks_is_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/belbin",
        json={"allocations": _VALID_ALLOCATIONS[:-1]},  # only 6 of 7 blocks
        headers=headers,
    )

    assert resp.status_code == 422, resp.text


async def test_belbin_cannot_be_retaken_alone(client: AsyncClient, db_session: AsyncSession) -> None:
    """One Belbin per assessment — a retake is the whole diagnostic (a new
    assessment), never Belbin alone."""
    _, assessment, headers = await _auth(db_session)

    first = await client.post(
        f"/api/v1/assessment/{assessment.id}/belbin",
        json={"allocations": _VALID_ALLOCATIONS}, headers=headers,
    )
    second = await client.post(
        f"/api/v1/assessment/{assessment.id}/belbin",
        json={"allocations": _VALID_ALLOCATIONS}, headers=headers,
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 409, second.text
    assert "Белбин" in second.json()["detail"]

    rows = (await db_session.execute(
        select(BelbinRun).where(BelbinRun.assessment_id == assessment.id)
    )).scalars().all()
    assert [r.id for r in rows] == [uuid.UUID(first.json()["run_id"])]


async def test_belongs_to_another_user_is_403(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, _ = await _auth(db_session)
    _, _, other_headers = await _auth(db_session)

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/belbin",
        json={"allocations": _VALID_ALLOCATIONS}, headers=other_headers,
    )

    assert resp.status_code == 403
    assert (
        await client.get(
            f"/api/v1/assessment/{assessment.id}/belbin/progress",
            headers=other_headers,
        )
    ).status_code == 403
    assert (
        await client.put(
            f"/api/v1/assessment/{assessment.id}/belbin/progress/0",
            json={"allocation": _VALID_ALLOCATIONS[0]},
            headers=other_headers,
        )
    ).status_code == 403


async def test_nonexistent_assessment_is_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, _, headers = await _auth(db_session)

    resp = await client.post(
        f"/api/v1/assessment/{uuid.uuid4()}/belbin",
        json={"allocations": _VALID_ALLOCATIONS}, headers=headers,
    )

    assert resp.status_code == 404
