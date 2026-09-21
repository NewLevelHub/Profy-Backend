"""PRO-337 × KZ-405: a report is stored as one AnalysisResult row per locale,
but it is reviewed once. A language switch must neither hide a published
report behind "under review" again nor start a second review, and a review
edit must not let a translation of the pre-edit text reach the student."""

import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult, ReviewStatus
from app.models.analysis_result_review_edit import AnalysisResultReviewEdit
from app.models.user import User
from app.services import assessment_shared

from tests.integration.review_helpers import (
    assign,
    capture_emails,
    force_complete_senior,
    generate,
    make_student_assessment,
)


def _result_url(student: User, assessment_id: uuid.UUID) -> str:
    return f"/api/v1/psychologist/students/{student.id}/results/{assessment_id}"


async def _rows(db_session: AsyncSession, assessment_id: uuid.UUID) -> list[AnalysisResult]:
    result = await db_session.execute(
        select(AnalysisResult)
        .where(AnalysisResult.assessment_id == assessment_id)
        .order_by(AnalysisResult.created_at.asc())
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def _clear_report_cache(assessment_id: uuid.UUID) -> None:
    await assessment_shared.get_redis().delete(*assessment_shared.report_cache_keys(assessment_id))


async def _switch_owner_locale(
    db_session: AsyncSession, student: User, assessment_id: uuid.UUID, locale: str
) -> None:
    # Same as the KZ-406 tests: the owner-locale pointer is cached, so a
    # locale change must drop it for the next request to see the new locale.
    student.locale = locale
    await db_session.flush()
    await _clear_report_cache(assessment_id)


async def test_translation_of_a_published_report_is_published_and_not_requeued(
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
    (ru_row,) = await _rows(db_session, assessment.id)
    ru_row.review_status = ReviewStatus.published
    await db_session.flush()

    await _switch_owner_locale(db_session, test_user, assessment.id, "kk")
    translated = await generate(client, auth_headers, assessment)
    assert translated.status_code == 200
    assert "status" not in translated.json()

    rows = await _rows(db_session, assessment.id)
    assert {r.locale: r.review_status for r in rows} == {
        "ru": ReviewStatus.published,
        "kk": ReviewStatus.published,
    }
    # Only the first-ever generation asks the psychologist for a review.
    emails["pending"].assert_awaited_once()

    fetched = await client.get(f"/api/v1/result/{assessment.id}", headers=auth_headers)
    assert fetched.status_code == 200
    assert "status" not in fetched.json()

    await _clear_report_cache(assessment.id)


async def test_pending_report_stays_hidden_in_every_locale_and_is_queued_once(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    test_user: User,
    psychologist_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    assessment = await make_student_assessment(db_session, test_user)
    await assign(client, admin_headers, psychologist_user, test_user)
    envelope = {"status": "pending_review", "assessment_id": str(assessment.id)}

    await generate(client, auth_headers, assessment)
    await _switch_owner_locale(db_session, test_user, assessment.id, "kk")

    # Not 404 report_locale_not_generated: an unreviewed report is hidden in
    # every locale, including one it hasn't been translated into yet.
    fetched = await client.get(f"/api/v1/result/{assessment.id}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json() == envelope
    generated = await generate(client, auth_headers, assessment)
    assert generated.json() == envelope

    rows = await _rows(db_session, assessment.id)
    assert sorted(r.locale for r in rows) == ["kk", "ru"]
    assert all(r.review_status == ReviewStatus.pending_review for r in rows)

    queue = (await client.get("/api/v1/psychologist/reviews", headers=psychologist_headers)).json()
    assert [item["assessment_id"] for item in queue] == [str(assessment.id)]

    await _clear_report_cache(assessment.id)


async def test_review_edit_drops_stale_translations_and_retranslation_is_published(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    test_user: User,
    psychologist_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    assessment = await make_student_assessment(db_session, test_user)
    await assign(client, admin_headers, psychologist_user, test_user)

    await generate(client, auth_headers, assessment)
    await _switch_owner_locale(db_session, test_user, assessment.id, "kk")
    await generate(client, auth_headers, assessment)
    assert len(await _rows(db_session, assessment.id)) == 2

    patched = await client.patch(
        _result_url(test_user, assessment.id),
        json={"summary": "Отредактировано психологом"},
        headers=psychologist_headers,
    )
    assert patched.status_code == 200
    # The edit lands on the original (ru) row; the kk translation was made
    # from the text before the edit, so it is gone.
    rows = await _rows(db_session, assessment.id)
    assert [(r.locale, r.summary) for r in rows] == [("ru", "Отредактировано психологом")]

    published = await client.post(f"{_result_url(test_user, assessment.id)}/publish", headers=psychologist_headers)
    assert published.status_code == 200

    # The owner is on kk: the missing translation is re-made from the reviewed
    # row and inherits its published status.
    missing = await client.get(f"/api/v1/result/{assessment.id}", headers=auth_headers)
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "report_locale_not_generated"
    regenerated = await generate(client, auth_headers, assessment)
    assert regenerated.status_code == 200
    assert "status" not in regenerated.json()

    rows = await _rows(db_session, assessment.id)
    assert {r.locale: r.review_status for r in rows} == {
        "ru": ReviewStatus.published,
        "kk": ReviewStatus.published,
    }

    await _clear_report_cache(assessment.id)


async def test_publish_without_edits_publishes_every_locale_row(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    test_user: User,
    psychologist_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    assessment = await make_student_assessment(db_session, test_user)
    await assign(client, admin_headers, psychologist_user, test_user)

    await generate(client, auth_headers, assessment)
    await _switch_owner_locale(db_session, test_user, assessment.id, "kk")
    await generate(client, auth_headers, assessment)

    published = await client.post(f"{_result_url(test_user, assessment.id)}/publish", headers=psychologist_headers)
    assert published.status_code == 200

    rows = await _rows(db_session, assessment.id)
    assert sorted(r.locale for r in rows) == ["kk", "ru"]
    assert all(r.review_status == ReviewStatus.published for r in rows)

    fetched = await client.get(f"/api/v1/result/{assessment.id}", headers=auth_headers)
    assert fetched.status_code == 200
    assert "status" not in fetched.json()

    await _clear_report_cache(assessment.id)


async def test_translation_keeps_psychologist_edits_outside_the_narrative(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    test_user: User,
    psychologist_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the narrative is translated. Careers, motivation highlights and
    the personality correction must come over from the reviewed row, or the
    translation inherits `published` while silently undoing the review."""
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    assessment = await make_student_assessment(db_session, test_user)
    await assign(client, admin_headers, psychologist_user, test_user)
    await generate(client, auth_headers, assessment)

    detail = (await client.get(_result_url(test_user, assessment.id), headers=psychologist_headers)).json()
    assert len(detail["careers"]) > 1
    kept_raw = detail["careers"][1]
    kept = {
        k: kept_raw[k]
        for k in [
            "slug", "name", "holland_code", "match_score", "description",
            "professions", "skills_needed", "subjects_to_develop", "first_steps"
        ]
        if k in kept_raw
    }
    kept["description"] = "Психолог переписал описание."
    kept["skills_needed"] = ["Психолог: главный навык."]
    # Longer than motivation_top on purpose: the response must not truncate it.
    edited_highlights = [f"Психолог: мотивация {n}." for n in range(1, 6)]
    patched = await client.patch(
        _result_url(test_user, assessment.id),
        json={
            "careers": [kept],
            "motivation_highlights": edited_highlights,
            "personality_notes": {**detail["personality_notes"], "openness": "Психолог: про открытость."},
        },
        headers=psychologist_headers,
    )
    if patched.status_code != 200:
        print("PATCH FAILED:", patched.json())
    assert patched.status_code == 200
    published = await client.post(f"{_result_url(test_user, assessment.id)}/publish", headers=psychologist_headers)
    assert published.status_code == 200

    await _switch_owner_locale(db_session, test_user, assessment.id, "kk")
    translated = await generate(client, auth_headers, assessment)
    assert translated.status_code == 200
    body = translated.json()
    assert "status" not in body
    # The freshly generated response (cached as-is) shows the reviewed
    # content, not values recomputed from the scores.
    assert body["motivation_highlights"] == edited_highlights
    assert {n["trait"]: n["description"] for n in body["personality_notes"]}["openness"] == "Психолог: про открытость."

    kk = next(r for r in await _rows(db_session, assessment.id) if r.locale == "kk")
    assert kk.review_status == ReviewStatus.published
    assert [c["slug"] for c in kk.careers] == [kept["slug"]]
    assert kk.careers[0]["description"] == "Психолог переписал описание."
    assert kk.careers[0]["skills_needed"] == ["Психолог: главный навык."]
    assert kk.motivation_highlights == edited_highlights
    assert kk.personality_notes_override == {"openness": "Психолог: про открытость."}

    await _clear_report_cache(assessment.id)


async def test_edit_history_moves_with_the_row_under_review(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    test_user: User,
    psychologist_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A kk-first report: the first edit is recorded on the kk row. Once a ru
    translation exists it becomes the row under review, and the next edit
    drops the kk row — its history must move to ru, not cascade away, or a
    later kk re-translation reverts the rewritten description."""
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    test_user.locale = "kk"
    await db_session.flush()
    assessment = await make_student_assessment(db_session, test_user)
    await assign(client, admin_headers, psychologist_user, test_user)
    url = _result_url(test_user, assessment.id)
    await generate(client, auth_headers, assessment)

    detail = (await client.get(url, headers=psychologist_headers)).json()
    careers = [dict(c) for c in detail["careers"]]
    careers[0]["description"] = "Психолог переписал описание."
    assert (await client.patch(url, json={"careers": careers}, headers=psychologist_headers)).status_code == 200

    await _switch_owner_locale(db_session, test_user, assessment.id, "ru")
    await generate(client, auth_headers, assessment)
    assert (await client.patch(url, json={"summary": "Вторая правка"}, headers=psychologist_headers)).status_code == 200

    (ru_row,) = await _rows(db_session, assessment.id)
    assert ru_row.locale == "ru"
    history = (
        await db_session.execute(
            select(AnalysisResultReviewEdit).where(AnalysisResultReviewEdit.analysis_result_id == ru_row.id)
        )
    ).scalars().all()
    assert len(history) == 2

    assert (await client.post(f"{url}/publish", headers=psychologist_headers)).status_code == 200
    await _switch_owner_locale(db_session, test_user, assessment.id, "kk")
    await generate(client, auth_headers, assessment)

    kk = next(r for r in await _rows(db_session, assessment.id) if r.locale == "kk")
    assert kk.review_status == ReviewStatus.published
    assert kk.careers[0]["description"] == "Психолог переписал описание."

    await _clear_report_cache(assessment.id)


async def test_fallback_translation_keeps_edited_narrative_verbatim(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    test_user: User,
    psychologist_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the LLM off (force_complete_senior) the new locale's narrative is
    the deterministic fallback — fresh text, not a translation of the reviewed
    row. Narrative fields the psychologist edited must come over verbatim;
    untouched ones keep the target-locale fallback."""
    capture_emails(monkeypatch)
    force_complete_senior(monkeypatch)
    assessment = await make_student_assessment(db_session, test_user)
    await assign(client, admin_headers, psychologist_user, test_user)
    url = _result_url(test_user, assessment.id)
    await generate(client, auth_headers, assessment)

    cards = [{"title": "Психолог: карточка", "description": "Психолог: описание карточки."}]
    patched = await client.patch(
        url, json={"summary": "Психолог: сводка.", "strength_cards": cards}, headers=psychologist_headers
    )
    assert patched.status_code == 200
    assert (await client.post(f"{url}/publish", headers=psychologist_headers)).status_code == 200

    await _switch_owner_locale(db_session, test_user, assessment.id, "kk")
    translated = await generate(client, auth_headers, assessment)
    assert translated.status_code == 200

    kk = next(r for r in await _rows(db_session, assessment.id) if r.locale == "kk")
    assert kk.summary == "Психолог: сводка."
    assert kk.strength_cards == cards
    # final_analysis was not edited: it stays the Kazakh fallback text.
    assert set("әғқңөұүһі") & set(kk.final_analysis.lower())
    assert translated.json()["summary"] == "Психолог: сводка."

    await _clear_report_cache(assessment.id)
