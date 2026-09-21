"""PRO-338 Ф2.4: POST /assessment/{id}/belbin — one-shot submit, 7 blocks x
8 values, sum strictly 10 per block via ipsative_battery.validate_allocation
(422 otherwise), Σ per 8 roles aggregated immediately into role_totals."""
import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.belbin_run import BelbinRun
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import auth_service
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
    headers = {"Authorization": f"Bearer {auth_service.create_jwt_token(user.id)}"}
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


async def test_resubmit_appends_a_new_row_not_overwrite(
    client: AsyncClient, db_session: AsyncSession
) -> None:
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
    assert second.status_code == 201, second.text
    assert first.json()["run_id"] != second.json()["run_id"]

    rows = (await db_session.execute(
        select(BelbinRun).where(BelbinRun.assessment_id == assessment.id)
    )).scalars().all()
    assert len(rows) == 2


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


async def test_nonexistent_assessment_is_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, _, headers = await _auth(db_session)

    resp = await client.post(
        f"/api/v1/assessment/{uuid.uuid4()}/belbin",
        json={"allocations": _VALID_ALLOCATIONS}, headers=headers,
    )

    assert resp.status_code == 404
