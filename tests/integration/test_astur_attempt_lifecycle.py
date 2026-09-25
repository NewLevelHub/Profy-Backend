"""PRO-427 — АСТУР attempt lifecycle over the real API: attempts are opened
explicitly with content pinned to their bank version and locale, every
payload names its attempt, answers are explicit (answered / skipped),
partial attempts have no result, the last submit finalizes atomically,
completed attempts are frozen, retakes are explicit, marked as repeat
exposure and never shadow a finished result."""
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
    answered,
    complete_attempt,
    make_student,
    open_attempt,
    quick_payload,
    start,
    submit,
    v1_version_id,
)

BANK = v1_bank()


async def _runs(db: AsyncSession, assessment_id: uuid.UUID) -> list[AsturRun]:
    # Runs opened inside one test transaction share created_at; completion
    # time (python clock) and an open run last keep the order stable.
    runs = (await db.execute(select(AsturRun).where(AsturRun.assessment_id == assessment_id))).scalars()
    return sorted(runs, key=lambda r: (r.completed_at is None, r.completed_at or r.created_at))


async def _state(client: AsyncClient, assessment_id: uuid.UUID, headers: dict) -> dict:
    resp = await client.get(f"/api/v1/assessment/{assessment_id}/astur/state", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _awareness(run_id, **kwargs) -> dict:
    return {"run_id": str(run_id), "answers": answered(content_answers(BANK, **kwargs)["awareness"])}


# ── opening attempts: run first, content second ─────────────────────────────


async def test_not_started_until_an_attempt_is_opened(client: AsyncClient, db_session: AsyncSession) -> None:
    _, assessment, headers = await make_student(db_session)
    assert (await _state(client, assessment.id, headers))["status"] == "not_started"
    assert await _runs(db_session, assessment.id) == []


async def test_opening_pins_version_and_locale_and_returns_that_content(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await make_student(db_session)
    body = await open_attempt(client, assessment.id, headers)
    again = await open_attempt(client, assessment.id, headers)

    assert body["run"]["run_id"] == again["run"]["run_id"] == body["content"]["run_id"]
    assert body["run"]["status"] == "in_progress"
    assert body["run"]["locale"] == body["content"]["locale"] == "ru"
    assert body["content"]["bank_version"] == body["run"]["bank_version"] == 1
    [run] = await _runs(db_session, assessment.id)
    assert run.bank_version_id == await v1_version_id(db_session)


async def test_started_subtest_is_resumed_without_resetting_its_clock(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await make_student(db_session)
    body = await open_attempt(client, assessment.id, headers)
    run_id = body["run"]["run_id"]

    first = await start(client, assessment.id, 1, run_id, headers)
    second = await start(client, assessment.id, 1, run_id, headers)
    resumed = await open_attempt(client, assessment.id, headers)

    assert first.status_code == second.status_code == 201
    assert first.json()["started_at"] == second.json()["started_at"]
    assert resumed["run"]["subtest_started_at"]["awareness"] == first.json()["started_at"]


async def test_content_and_scoring_stay_in_the_attempts_locale(client: AsyncClient, db_session: AsyncSession) -> None:
    user, assessment, headers = await make_student(db_session)
    await open_attempt(client, assessment.id, headers)  # RU attempt
    user.locale = "kk"  # the app's language switcher
    await db_session.flush()

    resumed = await open_attempt(client, assessment.id, headers)
    first_item = resumed["content"]["subtests"][0]["items"][0]
    assert resumed["content"]["locale"] == "ru"
    assert first_item["text"] == BANK.subtest("awareness").items[0]["text"]["ru"]

    await complete_attempt(client, assessment.id, headers)
    [run] = await _runs(db_session, assessment.id)
    assert run.locale == "ru"
    assert run.result_snapshot["overall_percent"] == 100.0


async def test_kk_attempt_stays_kk(client: AsyncClient, db_session: AsyncSession) -> None:
    user, assessment, headers = await make_student(db_session)
    user.locale = "kk"
    await db_session.flush()
    body = await open_attempt(client, assessment.id, headers)
    assert body["run"]["locale"] == "kk"
    user.locale = "ru"
    await db_session.flush()
    resumed = await open_attempt(client, assessment.id, headers)
    assert resumed["content"]["locale"] == "kk"
    assert resumed["content"]["subtests"][0]["name"] == BANK.subtest("awareness").name["kk"]


async def test_publish_between_opening_and_answering_never_rescores_with_new_keys(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, assessment, headers = await make_student(db_session)
    body = await open_attempt(client, assessment.id, headers)  # content v1 on screen
    await _publish_v2_with_new_awareness_key(db_session, user.id)

    await complete_attempt(client, assessment.id, headers)
    [run] = await _runs(db_session, assessment.id)
    assert run.id == uuid.UUID(body["run"]["run_id"])
    assert run.result_snapshot["bank_version"] == 1
    assert run.result_snapshot["item_scores"]["awareness-01"] == 1


# ── run_id guards ───────────────────────────────────────────────────────────


async def test_submit_for_another_attempt_is_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    _, assessment, headers = await make_student(db_session)
    await open_attempt(client, assessment.id, headers)
    resp = await submit(client, assessment.id, 1, _awareness(uuid.uuid4()), headers)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "astur_run_mismatch"
    assert (await start(client, assessment.id, 1, uuid.uuid4(), headers)).status_code == 409


async def test_submit_to_a_completed_attempt_is_rejected_and_changes_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await make_student(db_session)
    await complete_attempt(client, assessment.id, headers)
    [run] = await _runs(db_session, assessment.id)
    frozen = dict(run.result_snapshot)

    resp = await submit(client, assessment.id, 1, _awareness(run.id, wrong={"awareness"}), headers)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "astur_attempt_completed"
    reopen = await client.post(f"/api/v1/assessment/{assessment.id}/astur/attempt", json={}, headers=headers)
    assert reopen.status_code == 409

    await db_session.refresh(run)
    assert run.result_snapshot == frozen
    assert len(await _runs(db_session, assessment.id)) == 1


async def test_identical_retry_is_a_no_op_and_a_different_payload_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await make_student(db_session)
    run_id = (await open_attempt(client, assessment.id, headers))["run"]["run_id"]
    first = await submit(client, assessment.id, 1, _awareness(run_id), headers)
    retry = await submit(client, assessment.id, 1, _awareness(run_id), headers)
    changed = await submit(client, assessment.id, 1, _awareness(run_id, wrong={"awareness"}), headers)
    assert first.status_code == retry.status_code == 201
    assert changed.status_code == 409
    assert changed.json()["detail"]["code"] == "astur_subtest_already_submitted"


async def test_double_submit_of_the_final_block_is_answered_as_success(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await make_student(db_session)
    await complete_attempt(client, assessment.id, headers, skip={"lability"})
    run_id = (await _runs(db_session, assessment.id))[0].id
    payload = quick_payload(BANK, run_id)
    first = await submit(client, assessment.id, 3, payload, headers)
    second = await submit(client, assessment.id, 3, payload, headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["run_completed"] is second.json()["run_completed"] is True
    assert len(await _runs(db_session, assessment.id)) == 1


# ── explicit answers ────────────────────────────────────────────────────────


async def test_answered_values_are_validated_and_blank_is_never_an_answer(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await make_student(db_session)
    run_id = (await open_attempt(client, assessment.id, headers))["run"]["run_id"]
    numbers = answered(content_answers(BANK)["numeric_series"])
    numbers["1"] = {"status": "answered", "value": ["", ""]}
    resp = await submit(client, assessment.id, 7, {"run_id": run_id, "answers": numbers}, headers)
    assert resp.status_code == 422
    assert resp.json()["detail"]["invalid_items"] == ["1"]

    awareness = answered(content_answers(BANK)["awareness"])
    awareness["2"] = {"status": "answered", "value": "нет такого варианта"}
    resp = await submit(client, assessment.id, 1, {"run_id": run_id, "answers": awareness}, headers)
    assert resp.status_code == 422


async def test_skips_are_kept_apart_from_wrong_answers(client: AsyncClient, db_session: AsyncSession) -> None:
    _, assessment, headers = await make_student(db_session)
    run_id = (await open_attempt(client, assessment.id, headers))["run"]["run_id"]
    numbers = answered(content_answers(BANK, wrong={"numeric_series"})["numeric_series"])
    numbers["1"] = {"status": "skipped", "value": None}
    numbers["2"] = {"status": "skipped", "value": None}
    assert (await submit(client, assessment.id, 7, {"run_id": run_id, "answers": numbers}, headers)).status_code == 201
    await complete_attempt(client, assessment.id, headers, skip={"numeric_series"})

    [run] = await _runs(db_session, assessment.id)
    series = next(s for s in run.result_snapshot["subtests"] if s["key"] == "numeric_series")
    assert (series["answered"], series["skipped"], series["unanswered"]) == (13, 2, 0)
    assert run.result_snapshot["item_status"]["numeric_series-01"] == "skipped"
    assert run.result_snapshot["item_status"]["numeric_series-03"] == "wrong"
    assert run.answers["numeric_series"]["1"] == {"status": "skipped", "value": None}


# ── partial vs complete ─────────────────────────────────────────────────────


async def test_partial_attempt_has_no_result(client: AsyncClient, db_session: AsyncSession) -> None:
    _, assessment, headers = await make_student(db_session)
    await complete_attempt(client, assessment.id, headers, skip={"geometric_figures"})

    state = await _state(client, assessment.id, headers)
    assert state["status"] == "in_progress"
    assert state["latest_completed_run"] is None
    assert "geometric_figures" not in state["active_run"]["submitted_subtests"]
    [run] = await _runs(db_session, assessment.id)
    assert run.result_snapshot is None
    assert await _build_intelligence_section(assessment.id, db_session) is None


async def test_last_submit_finalizes_and_freezes_the_result(client: AsyncClient, db_session: AsyncSession) -> None:
    _, assessment, headers = await make_student(db_session, age=15, grade=9)
    responses = await complete_attempt(client, assessment.id, headers)
    assert [r.json()["run_completed"] for r in responses] == [False] * 7 + [True]

    [run] = await _runs(db_session, assessment.id)
    assert run.status == AsturRunStatus.completed
    assert run.scoring_version == "3"
    snapshot = run.result_snapshot
    assert snapshot["bank_version"] == 1
    assert snapshot["overall_percent"] == 100.0
    assert (snapshot["age_at_completion"], snapshot["grade_at_completion"]) == (15, 9)
    assert snapshot["history"] == {"attempt_number": 1, "repeat_exposure": False, "days_since_previous": None}
    assert run.protocol_quality["ok"] is True
    # The quick block is server-timed too (start + submit).
    assert snapshot["quick_instructions"]["server_block_ms"] is not None

    section = await _build_intelligence_section(assessment.id, db_session)
    assert section.run_id == run.id
    assert section.retake_in_progress is False
    assert (await _state(client, assessment.id, headers))["status"] == "completed"


async def test_result_does_not_follow_later_profile_changes(client: AsyncClient, db_session: AsyncSession) -> None:
    user, assessment, headers = await make_student(db_session, age=14, grade=8)
    await complete_attempt(client, assessment.id, headers)
    profile = (await db_session.execute(select(Profile).where(Profile.user_id == user.id))).scalar_one()
    profile.age, profile.grade = 17, 11
    await db_session.flush()

    section = await _build_intelligence_section(assessment.id, db_session)
    assert (section.age_at_completion, section.grade_at_completion) == (14, 8)


# ── retake ──────────────────────────────────────────────────────────────────


async def test_retake_is_explicit_idempotent_and_never_shadows_the_result(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await make_student(db_session)
    await complete_attempt(client, assessment.id, headers)
    [first] = await _runs(db_session, assessment.id)

    retake = await open_attempt(client, assessment.id, headers, retake=True)
    again = await open_attempt(client, assessment.id, headers, retake=True)
    assert retake["run"]["run_id"] == again["run"]["run_id"] != str(first.id)

    await complete_attempt(client, assessment.id, headers, wrong={"awareness"}, skip={"lability", "geometric_figures"})
    state = await _state(client, assessment.id, headers)
    assert state["status"] == "in_progress"
    assert state["latest_completed_run"]["run_id"] == str(first.id)
    section = await _build_intelligence_section(assessment.id, db_session)
    assert section.run_id == first.id
    assert section.retake_in_progress is True
    assert section.overall_percent == 100.0


async def test_finished_retake_is_shown_and_marked_as_repeat_exposure(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await make_student(db_session)
    await complete_attempt(client, assessment.id, headers)
    await complete_attempt(client, assessment.id, headers, wrong={"awareness"}, retake=True)

    runs = await _runs(db_session, assessment.id)
    assert [r.status for r in runs] == [AsturRunStatus.completed, AsturRunStatus.completed]
    section = await _build_intelligence_section(assessment.id, db_session)
    assert section.run_id == runs[1].id
    assert section.history.attempt_number == 2
    assert section.history.repeat_exposure is True
    assert section.history.days_since_previous == 0
    assert "repeat_exposure" in {f.code for f in section.protocol_quality.flags}
    assert next(s for s in section.subtests if s.key == "awareness").percent == 0.0
    assert runs[0].result_snapshot["overall_percent"] == 100.0


async def test_repeat_exposure_counts_attempts_of_other_assessments(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, first_assessment, headers = await make_student(db_session)
    await complete_attempt(client, first_assessment.id, headers)
    _, second_assessment, headers = await make_student(db_session, user=user)
    await complete_attempt(client, second_assessment.id, headers)

    section = await _build_intelligence_section(second_assessment.id, db_session)
    assert section.history.repeat_exposure is True
    assert section.history.attempt_number == 2


# ── bank versions ───────────────────────────────────────────────────────────


async def _publish_v2_with_new_awareness_key(db: AsyncSession, admin_id: uuid.UUID):
    from tests.unit.test_astur_bank import reviewed

    draft = await bank_versions.create_draft(db, admin_id=admin_id)
    document = reviewed(draft.document)
    first = next(s for s in document["subtests"] if s["key"] == "awareness")["items"][0]
    first["options"] = {"ru": ["вариант А", "вариант Б"], "kk": ["А нұсқасы", "Б нұсқасы"]}
    first["answer"] = {"ru": "вариант Б", "kk": "Б нұсқасы"}
    await bank_versions.update_draft(db, draft.id, document=document, notes="v2 test")
    return await bank_versions.publish(db, draft.id, admin_id=admin_id, confirmed_item_ids={first["item_id"]})


async def test_retake_after_a_publish_uses_the_new_version(client: AsyncClient, db_session: AsyncSession) -> None:
    user, assessment, headers = await make_student(db_session)
    await complete_attempt(client, assessment.id, headers)
    v2 = await _publish_v2_with_new_awareness_key(db_session, user.id)

    body = await open_attempt(client, assessment.id, headers, retake=True)
    assert body["run"]["bank_version"] == v2.version
    assert body["content"]["subtests"][0]["items"][0]["options"] == ["вариант А", "вариант Б"]


# ── protocol ────────────────────────────────────────────────────────────────


async def test_server_timing_and_quick_timestamps_are_recorded(client: AsyncClient, db_session: AsyncSession) -> None:
    _, assessment, headers = await make_student(db_session)
    run_id = (await open_attempt(client, assessment.id, headers))["run"]["run_id"]
    started = await start(client, assessment.id, 1, run_id, headers)
    assert started.status_code == 201 and started.json()["subtest"] == "awareness"
    resp = await submit(client, assessment.id, 1, _awareness(run_id), headers)
    assert isinstance(resp.json()["actual_ms"], int)

    await start(client, assessment.id, 3, run_id, headers)
    quick = await submit(client, assessment.id, 3, quick_payload(BANK, run_id, over_limit={8}), headers)
    assert quick.json()["over_limit_items"] == ["8"]

    [run] = await _runs(db_session, assessment.id)
    assert {"awareness", "lability"} <= run.subtest_timings_ms.keys()
    assert run.client_timezone == "Asia/Almaty"
    assert all(e["answered_at"] and e["status"] == "answered" for e in run.lability_answers.values())
    assert run.lability_answers["8"]["over_limit"] is True


async def test_implausible_quick_times_are_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    _, assessment, headers = await make_student(db_session)
    run_id = (await open_attempt(client, assessment.id, headers))["run"]["run_id"]
    payload = quick_payload(BANK, run_id)
    payload["elapsed_ms"]["1"] = -5
    assert (await submit(client, assessment.id, 3, payload, headers)).status_code == 422
    payload["elapsed_ms"]["1"] = BANK.lability_item_limit_ms * 100
    assert (await submit(client, assessment.id, 3, payload, headers)).status_code == 422


async def test_over_limit_and_missing_timing_reach_protocol_quality(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await make_student(db_session)
    run_id = (await open_attempt(client, assessment.id, headers))["run"]["run_id"]
    analogies = {"run_id": run_id, "answers": answered(content_answers(BANK)["analogies"])}
    await submit(client, assessment.id, 2, analogies, headers)  # no /start → no timing
    await submit(client, assessment.id, 3, quick_payload(BANK, run_id, over_limit={1, 2, 3}), headers)
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
    run_id = (await open_attempt(client, assessment.id, headers))["run"]["run_id"]
    resp = await submit(client, assessment.id, 1, {"run_id": run_id, "answers": answered({"1": "x"})}, headers)
    assert resp.status_code == 422
    assert "2" in resp.json()["detail"]["missing_items"]


async def test_unknown_subtest_is_404_and_foreign_assessment_is_403(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, assessment, headers = await make_student(db_session)
    _, _, other_headers = await make_student(db_session)
    run_id = (await open_attempt(client, assessment.id, headers))["run"]["run_id"]
    assert (await submit(client, assessment.id, 99, {"run_id": run_id, "answers": {}}, headers)).status_code == 404
    assert (await client.get(f"/api/v1/assessment/{assessment.id}/astur/state", headers=other_headers)).status_code == 403
    foreign = await client.post(f"/api/v1/assessment/{assessment.id}/astur/attempt", json={}, headers=other_headers)
    assert foreign.status_code == 403


# ── legacy ──────────────────────────────────────────────────────────────────


async def test_legacy_completed_attempt_is_frozen_once_under_the_legacy_formula(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, assessment, _ = await make_student(db_session)
    lability = {
        key: {"answer": entry["value"], "elapsed_ms": 1000, "over_limit": False}
        for key, entry in quick_payload(BANK, uuid.uuid4())["answers"].items()
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
    assert section.overall_percent == 100.0
    assert next(s for s in section.subtests if s.key == "geometric_figures").in_overall is False
