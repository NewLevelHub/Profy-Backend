"""Psychologist review queue, edit and publish (PRO-337,
docs/psychologist-review-gate-plan.md §3–§4)."""

import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result_review_edit import AnalysisResultReviewEdit
from app.models.user import User

from tests.integration.review_helpers import (
    STUDENT_NAME,
    answer_legacy_big_five,
    assign,
    capture_emails,
    force_complete_senior,
    generate,
    make_student_assessment,
    stored_result,
)


def _result_url(student: User, assessment_id: uuid.UUID) -> str:
    return f"/api/v1/psychologist/students/{student.id}/results/{assessment_id}"


async def test_review_endpoints_require_psychologist(
    client: httpx.AsyncClient, auth_headers: dict[str, str], admin_headers: dict[str, str]
) -> None:
    assert (await client.get("/api/v1/psychologist/reviews", headers=auth_headers)).status_code == 403
    assert (await client.get("/api/v1/psychologist/reviews", headers=admin_headers)).status_code == 403


async def test_queue_lists_only_assigned_pending_results(
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
    await generate(client, auth_headers, assessment)

    before = await client.get("/api/v1/psychologist/reviews", headers=psychologist_headers)
    assert before.json() == []

    # Assigned after generation — the existing result is pulled in live.
    await assign(db_session, psychologist_user, test_user)
    queue = (await client.get("/api/v1/psychologist/reviews", headers=psychologist_headers)).json()
    assert len(queue) == 1
    item = queue[0]
    assert item["assessment_id"] == str(assessment.id)
    assert item["student_id"] == str(test_user.id)
    assert item["student_name"] == STUDENT_NAME
    assert item["student_email"] == test_user.email
    assert item["age"] == 16
    assert item["goal"] == "explore"
    assert item["reviewed_at"] is None

    published = await client.post(f"{_result_url(test_user, assessment.id)}/publish", headers=psychologist_headers)
    assert published.status_code == 200
    after = await client.get("/api/v1/psychologist/reviews", headers=psychologist_headers)
    assert after.json() == []


async def test_result_detail_requires_assignment_and_ownership(
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
    await generate(client, auth_headers, assessment)

    unassigned = await client.get(_result_url(test_user, assessment.id), headers=psychologist_headers)
    assert unassigned.status_code == 404

    await assign(db_session, psychologist_user, test_user)
    detail = await client.get(_result_url(test_user, assessment.id), headers=psychologist_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["review_status"] == "pending_review"
    assert body["summary"]
    assert isinstance(body["big_five"], dict)
    assert isinstance(body["careers"], list)

    unknown = await client.get(_result_url(test_user, uuid.uuid4()), headers=psychologist_headers)
    assert unknown.status_code == 404


async def test_patch_edits_content_audits_and_publish_shows_it_to_student(
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
    await generate(client, auth_headers, assessment)
    await assign(db_session, psychologist_user, test_user)
    original_summary = (await stored_result(db_session, assessment.id)).summary

    patched = await client.patch(
        _result_url(test_user, assessment.id),
        json={
            "summary": "Отредактировано психологом",
            "final_analysis": "Итог от психолога",
            "strength_cards": [{"title": "Упорство", "description": "Доводишь дело до конца"}],
        },
        headers=psychologist_headers,
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["summary"] == "Отредактировано психологом"
    assert body["reviewed_by"] == str(psychologist_user.id)
    assert body["reviewed_at"] is not None
    assert body["review_status"] == "pending_review"

    stored = await stored_result(db_session, assessment.id)
    edits = (
        await db_session.execute(
            select(AnalysisResultReviewEdit).where(AnalysisResultReviewEdit.analysis_result_id == stored.id)
        )
    ).scalars().all()
    assert len(edits) == 1
    assert edits[0].editor_id == psychologist_user.id
    assert set(edits[0].changed_fields) == {"summary", "final_analysis", "strength_cards"}
    assert edits[0].changed_fields["summary"]["old"] == original_summary

    # Same values again — nothing changed, no second audit row.
    await client.patch(
        _result_url(test_user, assessment.id),
        json={"summary": "Отредактировано психологом"},
        headers=psychologist_headers,
    )
    edits_after = (
        await db_session.execute(
            select(AnalysisResultReviewEdit).where(AnalysisResultReviewEdit.analysis_result_id == stored.id)
        )
    ).scalars().all()
    assert len(edits_after) == 1

    still_hidden = await client.get(f"/api/v1/result/{assessment.id}", headers=auth_headers)
    assert still_hidden.json()["status"] == "pending_review"

    await client.post(f"{_result_url(test_user, assessment.id)}/publish", headers=psychologist_headers)
    student_view = await client.get(f"/api/v1/result/{assessment.id}", headers=auth_headers)
    assert student_view.status_code == 200
    student_body = student_view.json()
    assert student_body["summary"] == "Отредактировано психологом"
    assert student_body["final_analysis"] == "Итог от психолога"
    assert student_body["strength_cards"] == [{"title": "Упорство", "description": "Доводишь дело до конца"}]

    from app.services import assessment_shared

    await assessment_shared.get_redis().delete(assessment_shared.report_cache_key(assessment.id))


async def test_personality_note_edit_reaches_the_student(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    test_user: User,
    psychologist_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """"Твой характер" is computed from the scores, not read from storage —
    a correction has to override that computed phrase, and only for the
    trait actually corrected."""
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    assessment = await make_student_assessment(db_session, test_user)
    await answer_legacy_big_five(db_session, assessment)
    await generate(client, auth_headers, assessment)
    await assign(db_session, psychologist_user, test_user)

    detail = await client.get(_result_url(test_user, assessment.id), headers=psychologist_headers)
    notes = detail.json()["personality_notes"]
    assert set(notes) == {
        "openness", "conscientiousness", "extraversion", "agreeableness", "emotional_stability",
    }
    corrected = "Психолог: тебе легко браться за незнакомое."

    patched = await client.patch(
        _result_url(test_user, assessment.id),
        json={"personality_notes": {**notes, "openness": corrected}},
        headers=psychologist_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["personality_notes"]["openness"] == corrected

    stored = await stored_result(db_session, assessment.id)
    # Only the corrected trait is stored — the rest keep following the scores.
    assert set(stored.personality_notes_override) == {"openness"}

    await client.post(f"{_result_url(test_user, assessment.id)}/publish", headers=psychologist_headers)
    student_view = await client.get(f"/api/v1/result/{assessment.id}", headers=auth_headers)
    by_trait = {n["trait"]: n["description"] for n in student_view.json()["personality_notes"]}
    assert by_trait["openness"] == corrected
    assert by_trait["extraversion"] == notes["extraversion"]

    from app.services import assessment_shared

    await assessment_shared.get_redis().delete(assessment_shared.report_cache_key(assessment.id))


async def test_second_partial_personality_patch_keeps_earlier_corrections(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    test_user: User,
    psychologist_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omitting a trait means "leave as is", like every other patch field."""
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    assessment = await make_student_assessment(db_session, test_user)
    await answer_legacy_big_five(db_session, assessment)
    await generate(client, auth_headers, assessment)
    await assign(db_session, psychologist_user, test_user)
    url = _result_url(test_user, assessment.id)

    first = await client.patch(
        url, json={"personality_notes": {"openness": "Первая правка"}}, headers=psychologist_headers
    )
    assert first.status_code == 200
    second = await client.patch(
        url, json={"personality_notes": {"extraversion": "Вторая правка"}}, headers=psychologist_headers
    )
    assert second.status_code == 200
    notes = second.json()["personality_notes"]
    assert notes["openness"] == "Первая правка"
    assert notes["extraversion"] == "Вторая правка"

    stored = await stored_result(db_session, assessment.id)
    assert set(stored.personality_notes_override) == {"openness", "extraversion"}

    # Typing the computed phrase back in drops the override for that trait.
    default_openness = (
        await client.patch(
            url,
            json={"personality_notes": {"openness": "Первая правка"}},
            headers=psychologist_headers,
        )
    ).json()["personality_notes"]["openness"]
    assert default_openness == "Первая правка"


@pytest.mark.parametrize(
    "payload",
    [
        {"strengths": ["Z"]},
        {"personality_notes": {"нет_такой_черты": "текст"}},
        {"personality_notes": {"openness": "   "}},
        {"summary": None},
        {"summary": ""},
        {"profile": {"R": 100}},
        {"strength_cards": [{"title": "Без описания"}]},
    ],
)
async def test_patch_rejects_invalid_payloads(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    test_user: User,
    psychologist_user: User,
    monkeypatch: pytest.MonkeyPatch,
    payload: dict,
) -> None:
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    assessment = await make_student_assessment(db_session, test_user)
    await generate(client, auth_headers, assessment)
    await assign(db_session, psychologist_user, test_user)

    response = await client.patch(
        _result_url(test_user, assessment.id), json=payload, headers=psychologist_headers
    )
    assert response.status_code == 422


async def test_publish_is_irreversible_and_notifies_student(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    test_user: User,
    psychologist_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emails = capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    assessment = await make_student_assessment(db_session, test_user)
    await generate(client, auth_headers, assessment)
    await assign(db_session, psychologist_user, test_user)

    student_detail = await client.get(f"/api/v1/psychologist/students/{test_user.id}", headers=psychologist_headers)
    assert student_detail.json()["assessments"][0]["review_status"] == "pending_review"

    published = await client.post(f"{_result_url(test_user, assessment.id)}/publish", headers=psychologist_headers)
    assert published.status_code == 200
    body = published.json()
    assert body["review_status"] == "published"
    assert body["published_by"] == str(psychologist_user.id)
    assert body["published_at"] is not None
    # Published without edits — publishing counts as the review.
    assert body["reviewed_by"] == str(psychologist_user.id)
    emails["published"].assert_awaited_once_with(
        test_user.email, STUDENT_NAME, locale=test_user.locale, results_url="http://localhost:5173/results"
    )

    again = await client.post(f"{_result_url(test_user, assessment.id)}/publish", headers=psychologist_headers)
    assert again.status_code == 409
    edit = await client.patch(
        _result_url(test_user, assessment.id), json={"summary": "поздно"}, headers=psychologist_headers
    )
    assert edit.status_code == 409

    student_detail = await client.get(f"/api/v1/psychologist/students/{test_user.id}", headers=psychologist_headers)
    assert student_detail.json()["assessments"][0]["review_status"] == "published"

    from app.services import assessment_shared

    await assessment_shared.get_redis().delete(assessment_shared.report_cache_key(assessment.id))


async def test_personality_notes_follow_the_report_language_not_the_reviewer(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    test_user: User,
    psychologist_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A psychologist browsing in kk reviewing a ru report must see — and
    correct — the ru phrase, or the correction lands inside the ru report in
    the wrong language."""
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    assessment = await make_student_assessment(db_session, test_user)
    await generate(client, auth_headers, assessment)
    await assign(db_session, psychologist_user, test_user)

    url = _result_url(test_user, assessment.id)
    in_ru = await client.get(url, headers={**psychologist_headers, "Accept-Language": "ru"})
    in_kk = await client.get(url, headers={**psychologist_headers, "Accept-Language": "kk"})
    assert in_ru.status_code == in_kk.status_code == 200
    assert in_kk.json()["personality_notes"] == in_ru.json()["personality_notes"]
    assert not any(set("әғқңөұүһі") & set(text.lower()) for text in in_kk.json()["personality_notes"].values())
