"""PRO-427 — АСТУР attempt lifecycle over the real API: partial attempts
have no result, the last submit finalizes atomically, completed attempts are
frozen, retakes are explicit and never shadow a finished result, and every
attempt is scored with the bank version it was pinned to."""
import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.astur_run import AsturRun, AsturRunStatus
from app.models.profile import Profile
from app.services.astur import bank_versions
from app.services.astur.runs import freeze_legacy_snapshot
from app.services.new_tests_report_service import _build_intelligence_section
from tests.astur_fixtures import content_answers, v1_bank
from tests.integration.astur_helpers import (
    complete_attempt,
    make_student,
    quick_payload,
    submit,
    v1_version_id,
)

BANK = v1_bank()


async def _runs(db: AsyncSession, assessment_id: uuid.UUID) -> list[AsturRun]:
    return list((await db.execute(
        select(AsturRun).where(AsturRun.assessment_id == assessment_id).order_by(AsturRun.created_at)
    )).scalars())


async def _state(client: AsyncClient, assessment_id: uuid.UUID, headers: dict) -> dict:
    resp = await client.get(f"/api/v1/assessment/{assessment_id}/astur/state", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── partial vs complete ─────────────────────────────────────────────────────


async def test_not_started_state(client: AsyncClient, db_session: AsyncSession) -> None:
    _, assessment, headers = await make_student(db_session)
    assert (await _state(client, assessment.id, headers))["status"] == "not_started"


async def test_partial_attempt_has_no_result(client: AsyncClient, db_session: AsyncSession) -> None:
    _, assessment, headers = await make_student(db_session)
    await complete_attempt(client, assessment.id, headers, skip={"geometric_figures"})

    state = await _state(client, assessment.id, headers)
    assert state["status"] == "in_progress"
    assert state["latest_completed_run"] is None
    assert "geometric_figures" not in state["active_run"]["submitted_subtests"]

    [run] = await _runs(db_session, assessment.id)
    assert run.status == AsturRunStatus.in_progress
    assert run.result_snapshot is None
    assert await _build_intelligence_section(assessment.id, db_session) is None


async def test_last_submit_finalizes_and_freezes_the_result(client: AsyncClient, db_session: AsyncSession) -> None:
    _, assessment, headers = await make_student(db_session, age=15, grade=9)
    responses = await complete_attempt(client, assessment.id, headers)
    assert [r.json()["run_completed"] for r in responses] == [False] * 7 + [True]

    [run] = await _runs(db_session, assessment.id)
    assert run.status == AsturRunStatus.completed
    assert run.completed_at is not None
    assert run.scoring_version == "3"
    assert run.content_hash is not None
    snapshot = run.result_snapshot
    assert snapshot["bank_version"] == 1
    assert snapshot["overall_percent"] == 100.0
    assert (snapshot["age_at_completion"], snapshot["grade_at_completion"]) == (15, 9)
    assert run.protocol_quality == snapshot["protocol_quality"]

    section = await _build_intelligence_section(assessment.id, db_session)
    assert section.run_id == run.id
    assert section.retake_in_progress is False
    assert {s.key for s in section.subtests} >= {"geometric_figures"}
    assert (await _state(client, assessment.id, headers))["status"] == "completed"


async def test_result_does_not_follow_later_profile_changes(client: AsyncClient, db_session: AsyncSession) -> None:
    user, assessment, headers = await make_student(db_session, age=14, grade=8)
    await complete_attempt(client, assessment.id, headers)
    profile = (await db_session.execute(select(Profile).where(Profile.user_id == user.id))).scalar_one()
    profile.age, profile.grade = 17, 11
    await db_session.flush()

    section = await _build_intelligence_section(assessment.id, db_session)
    assert (section.age_at_completion, section.grade_at_completion) == (14, 8)


async def test_submit_to_a_completed_attempt_is_rejected_and_changes_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await make_student(db_session)
    await complete_attempt(client, assessment.id, headers)
    [run] = await _runs(db_session, assessment.id)
    frozen = dict(run.result_snapshot)

    wrong = content_answers(BANK, wrong={"awareness"})["awareness"]
    resp = await submit(client, assessment.id, 1, {"answers": wrong}, headers)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "astur_attempt_completed"
    start = await client.post(f"/api/v1/assessment/{assessment.id}/astur/subtest/1/start", headers=headers)
    assert start.status_code == 409

    await db_session.refresh(run)
    assert run.result_snapshot == frozen
    assert len(await _runs(db_session, assessment.id)) == 1


# ── retake ──────────────────────────────────────────────────────────────────


async def test_retake_is_explicit_idempotent_and_never_shadows_the_result(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await make_student(db_session)
    await complete_attempt(client, assessment.id, headers)
    [first] = await _runs(db_session, assessment.id)

    retake = await client.post(f"/api/v1/assessment/{assessment.id}/astur/runs", headers=headers)
    again = await client.post(f"/api/v1/assessment/{assessment.id}/astur/runs", headers=headers)
    assert retake.status_code == again.status_code == 201
    assert retake.json()["run_id"] == again.json()["run_id"] != str(first.id)
    assert retake.json()["status"] == "in_progress"

    # Half-done retake: the finished result stays the one shown.
    await complete_attempt(client, assessment.id, headers, wrong={"awareness"}, skip={"lability", "geometric_figures"})
    state = await _state(client, assessment.id, headers)
    assert state["status"] == "in_progress"
    assert state["latest_completed_run"]["run_id"] == str(first.id)
    section = await _build_intelligence_section(assessment.id, db_session)
    assert section.run_id == first.id
    assert section.retake_in_progress is True
    assert section.overall_percent == 100.0


async def test_finished_retake_becomes_the_shown_result(client: AsyncClient, db_session: AsyncSession) -> None:
    _, assessment, headers = await make_student(db_session)
    await complete_attempt(client, assessment.id, headers)
    await client.post(f"/api/v1/assessment/{assessment.id}/astur/runs", headers=headers)
    await complete_attempt(client, assessment.id, headers, wrong={"awareness"})

    runs = await _runs(db_session, assessment.id)
    assert [r.status for r in runs] == [AsturRunStatus.completed, AsturRunStatus.completed]
    section = await _build_intelligence_section(assessment.id, db_session)
    assert section.run_id == runs[1].id
    assert section.retake_in_progress is False
    assert next(s for s in section.subtests if s.key == "awareness").percent == 0.0
    # The earlier attempt is untouched.
    assert runs[0].result_snapshot["overall_percent"] == 100.0


# ── bank versions ───────────────────────────────────────────────────────────


async def _publish_v2_with_new_awareness_key(db: AsyncSession, admin_id: uuid.UUID):
    draft = await bank_versions.create_draft(db, admin_id=admin_id)
    document = dict(draft.document)
    subtests = [dict(s) for s in document["subtests"]]
    awareness = next(s for s in subtests if s["key"] == "awareness")
    items = [dict(i) for i in awareness["items"]]
    first = items[0]
    first["options"] = {"ru": ["вариант А", "вариант Б"], "kk": ["А нұсқасы", "Б нұсқасы"]}
    first["answer"] = {"ru": "вариант Б", "kk": "Б нұсқасы"}
    awareness["items"] = items
    document["subtests"] = subtests
    await bank_versions.update_draft(db, draft.id, document=document, notes="v2 test")
    return await bank_versions.publish(db, draft.id, admin_id=admin_id, confirmed_item_ids={first["item_id"]})


async def test_attempt_is_scored_with_its_pinned_version_after_a_new_publish(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, assessment, headers = await make_student(db_session)
    # Open the attempt on v1, then publish v2 mid-attempt.
    await submit(client, assessment.id, 2, {"answers": content_answers(BANK)["analogies"]}, headers)
    v2 = await _publish_v2_with_new_awareness_key(db_session, user.id)
    assert v2.version == 2

    content = (await client.get(f"/api/v1/assessment/{assessment.id}/astur/content", headers=headers)).json()
    assert content["bank_version"] == 1
    await complete_attempt(client, assessment.id, headers, skip={"analogies"})

    [run] = await _runs(db_session, assessment.id)
    assert run.bank_version_id == await v1_version_id(db_session)
    assert run.result_snapshot["bank_version"] == 1
    assert run.result_snapshot["item_scores"]["awareness-01"] == 1

    # A retake opened now is pinned to v2 and served v2 content.
    await client.post(f"/api/v1/assessment/{assessment.id}/astur/runs", headers=headers)
    content = (await client.get(f"/api/v1/assessment/{assessment.id}/astur/content", headers=headers)).json()
    assert content["bank_version"] == 2
    assert content["subtests"][0]["items"][0]["options"] == ["вариант А", "вариант Б"]


# ── protocol ────────────────────────────────────────────────────────────────


async def test_server_timing_and_quick_timestamps_are_recorded(client: AsyncClient, db_session: AsyncSession) -> None:
    _, assessment, headers = await make_student(db_session)
    start = await client.post(f"/api/v1/assessment/{assessment.id}/astur/subtest/1/start", headers=headers)
    assert start.status_code == 201 and start.json()["subtest"] == "awareness"
    resp = await submit(client, assessment.id, 1, {"answers": content_answers(BANK)["awareness"]}, headers)
    assert isinstance(resp.json()["actual_ms"], int)

    quick = await submit(client, assessment.id, 3, quick_payload(BANK, over_limit={8}), headers)
    assert quick.json()["over_limit_items"] == ["8"]

    [run] = await _runs(db_session, assessment.id)
    assert "awareness" in run.subtest_timings_ms
    assert run.subtest_started_at == {}
    assert run.client_timezone == "Asia/Almaty"
    assert all("answered_at" in entry for entry in run.lability_answers.values())
    assert run.lability_answers["8"]["over_limit"] is True


async def test_over_limit_and_missing_timing_reach_protocol_quality(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await make_student(db_session)
    # Submit analogies without /start → no verified timing.
    await submit(client, assessment.id, 2, {"answers": content_answers(BANK)["analogies"]}, headers)
    await submit(client, assessment.id, 3, quick_payload(BANK, over_limit={1, 2, 3}), headers)
    await complete_attempt(client, assessment.id, headers, skip={"analogies", "lability"})

    [run] = await _runs(db_session, assessment.id)
    codes = {(f["code"], f["subtest"]) for f in run.protocol_quality["flags"]}
    assert ("subtest_timing_missing", "analogies") in codes
    assert ("quick_over_limit", "lability") in codes
    assert ("quick_insufficient_on_time", "lability") in codes
    assert run.protocol_quality["ok"] is False
    assert run.result_snapshot["quick_instructions"]["accuracy_change_pp"] is None


async def test_wrong_item_key_set_is_422(client: AsyncClient, db_session: AsyncSession) -> None:
    _, assessment, headers = await make_student(db_session)
    resp = await submit(client, assessment.id, 1, {"answers": {"1": "x"}}, headers)
    assert resp.status_code == 422
    assert "2" in resp.json()["detail"]["missing_items"]


async def test_elapsed_ms_rules(client: AsyncClient, db_session: AsyncSession) -> None:
    _, assessment, headers = await make_student(db_session)
    no_elapsed = quick_payload(BANK)
    no_elapsed.pop("elapsed_ms")
    assert (await submit(client, assessment.id, 3, no_elapsed, headers)).status_code == 422
    extra = {"answers": content_answers(BANK)["awareness"], "elapsed_ms": {"1": 1}}
    assert (await submit(client, assessment.id, 1, extra, headers)).status_code == 422


async def test_unknown_subtest_is_404_and_foreign_assessment_is_403(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await make_student(db_session)
    _, _, other_headers = await make_student(db_session)
    assert (await submit(client, assessment.id, 99, {"answers": {}}, headers)).status_code == 404
    assert (await client.get(f"/api/v1/assessment/{assessment.id}/astur/state", headers=other_headers)).status_code == 403
    assert (await client.post(f"/api/v1/assessment/{assessment.id}/astur/runs", headers=other_headers)).status_code == 403


# ── legacy ──────────────────────────────────────────────────────────────────


async def test_legacy_completed_attempt_is_frozen_once_under_the_legacy_formula(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, assessment, _ = await make_student(db_session)
    lability = {
        key: {"answer": value, "elapsed_ms": 1000, "over_limit": False}
        for key, value in quick_payload(BANK)["answers"].items()
    }
    run = AsturRun(
        assessment_id=assessment.id, user_id=user.id, bank_version_id=await v1_version_id(db_session),
        status=AsturRunStatus.completed, answers=content_answers(BANK, wrong={"geometric_figures"}),
        lability_answers=lability,
    )
    db_session.add(run)
    await db_session.flush()
    assert await _build_intelligence_section(assessment.id, db_session) is None  # not frozen yet

    await freeze_legacy_snapshot(db_session, run)
    await db_session.flush()

    section = await _build_intelligence_section(assessment.id, db_session)
    assert section.legacy is True
    assert section.scoring_version == "legacy-1"
    assert section.age_at_completion is None
    # Spatial is shown but, under the legacy formula, not counted.
    assert section.overall_percent == 100.0
    assert next(s for s in section.subtests if s.key == "geometric_figures").in_overall is False
