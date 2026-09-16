"""PRO-338 Ф3.4: POST /assessment/{id}/astur/subtest/{n}/start +
POST /assessment/{id}/astur/subtest/{n} — per-subtest submit so a long,
multi-subtest test never loses progress on a dropped connection. Server
times subtests 1-2/4-7 itself (started_at/submitted_at); lability (3) is
client-timed per-item with a server plausibility check."""
import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal
from app.models.astur_run import AsturRun
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import auth_service


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


def _awareness_answers() -> dict[str, str]:
    return {str(i): "x" for i in range(1, 21)}


def _lability_payload() -> tuple[dict[str, str], dict[str, int]]:
    answers = {str(i): "1" for i in range(1, 9)}
    elapsed_ms = {str(i): 1000 for i in range(1, 9)}
    return answers, elapsed_ms


async def test_start_then_submit_records_server_timed_elapsed_ms(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)

    start_resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/astur/subtest/1/start", headers=headers,
    )
    assert start_resp.status_code == 201, start_resp.text
    assert start_resp.json()["subtest"] == "awareness"

    submit_resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/astur/subtest/1",
        json={"answers": _awareness_answers()}, headers=headers,
    )
    assert submit_resp.status_code == 201, submit_resp.text
    body = submit_resp.json()
    assert body["subtest"] == "awareness"
    assert isinstance(body["actual_ms"], int)
    assert body["actual_ms"] >= 0

    run = (await db_session.execute(
        select(AsturRun).where(AsturRun.id == uuid.UUID(body["run_id"]))
    )).scalar_one()
    assert run.answers["awareness"] == _awareness_answers()
    assert "awareness" in run.subtest_timings_ms
    assert run.subtest_started_at == {}  # cleared once submitted


async def test_submit_without_start_is_still_accepted_with_no_timing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Ф3.4's own principle: never losing progress beats strict timer
    enforcement — a client that skips /start still gets its answer saved."""
    _, assessment, headers = await _auth(db_session)

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/astur/subtest/1",
        json={"answers": _awareness_answers()}, headers=headers,
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["actual_ms"] is None


async def test_wrong_item_key_set_is_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)
    bad_answers = _awareness_answers()
    del bad_answers["20"]  # only 19 of 20

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/astur/subtest/1",
        json={"answers": bad_answers}, headers=headers,
    )

    assert resp.status_code == 422, resp.text


async def test_two_subtests_accumulate_on_the_same_run(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)

    first = await client.post(
        f"/api/v1/assessment/{assessment.id}/astur/subtest/1",
        json={"answers": _awareness_answers()}, headers=headers,
    )
    second = await client.post(
        f"/api/v1/assessment/{assessment.id}/astur/subtest/4",
        json={"answers": {str(i): ["a", "b"] for i in range(1, 13)}}, headers=headers,
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["run_id"] == second.json()["run_id"]

    rows = (await db_session.execute(
        select(AsturRun).where(AsturRun.assessment_id == assessment.id)
    )).scalars().all()
    assert len(rows) == 1
    assert set(rows[0].answers.keys()) == {"awareness", "classification"}


async def test_lability_requires_elapsed_ms_and_flags_over_limit_items(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)
    answers, elapsed_ms = _lability_payload()
    elapsed_ms["3"] = 9000  # over the 5000ms default limit

    missing_elapsed = await client.post(
        f"/api/v1/assessment/{assessment.id}/astur/subtest/3",
        json={"answers": answers}, headers=headers,
    )
    assert missing_elapsed.status_code == 422

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/astur/subtest/3",
        json={"answers": answers, "elapsed_ms": elapsed_ms}, headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["over_limit_items"] == ["3"]

    run = (await db_session.execute(
        select(AsturRun).where(AsturRun.assessment_id == assessment.id)
    )).scalar_one()
    assert run.lability_answers["3"]["over_limit"] is True
    assert run.lability_answers["1"]["over_limit"] is False
    assert run.answers == {}  # lability never touches the scored `answers` dict


async def test_elapsed_ms_on_a_non_lability_subtest_is_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/astur/subtest/1",
        json={"answers": _awareness_answers(), "elapsed_ms": {"1": 100}}, headers=headers,
    )

    assert resp.status_code == 422


async def test_completing_the_full_battery_then_resubmitting_starts_a_new_run(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)

    # Complete every scored subtest + lability.
    subtest_payloads = {
        1: {"answers": {str(i): "x" for i in range(1, 21)}},
        2: {"answers": {str(i): "x" for i in range(1, 17)}},
        3: {"answers": {str(i): "1" for i in range(1, 9)}, "elapsed_ms": {str(i): 100 for i in range(1, 9)}},
        4: {"answers": {str(i): ["a", "b"] for i in range(1, 13)}},
        5: {"answers": {str(i): "x" for i in range(1, 20)}},
        6: {"answers": {str(i): ["a", "b"] for i in range(1, 9)}},
        7: {"answers": {str(i): [1, 2] for i in range(1, 16)}},
    }
    first_run_id = None
    for n, payload in subtest_payloads.items():
        resp = await client.post(
            f"/api/v1/assessment/{assessment.id}/astur/subtest/{n}", json=payload, headers=headers,
        )
        assert resp.status_code == 201, resp.text
        first_run_id = resp.json()["run_id"]

    # Battery is now complete — the next submit (e.g. a retake) must open a
    # NEW row, not keep appending to the finished one.
    retake = await client.post(
        f"/api/v1/assessment/{assessment.id}/astur/subtest/1",
        json={"answers": {str(i): "y" for i in range(1, 21)}}, headers=headers,
    )
    assert retake.status_code == 201, retake.text
    assert retake.json()["run_id"] != first_run_id

    rows = (await db_session.execute(
        select(AsturRun).where(AsturRun.assessment_id == assessment.id)
    )).scalars().all()
    assert len(rows) == 2


async def test_unknown_subtest_number_is_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await _auth(db_session)

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/astur/subtest/8",
        json={"answers": {}}, headers=headers,
    )

    assert resp.status_code == 404


async def test_belongs_to_another_user_is_403(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, _ = await _auth(db_session)
    _, _, other_headers = await _auth(db_session)

    resp = await client.post(
        f"/api/v1/assessment/{assessment.id}/astur/subtest/1",
        json={"answers": _awareness_answers()}, headers=other_headers,
    )

    assert resp.status_code == 403
