"""KZ-403 (end-to-end) — with the LLM off, a `locale='kk'` student's
`/results` renders in Kazakh: the deterministic narrative summary/final
analysis, the interest-map spheres and note, the personality note, and the
career "why" strings all come back Kazakh, driven by the artifact owner's
`users.locale` rather than any request locale.
"""
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import (
    assessment_shared,
    llm_client,
    motivation_pair_service,
    motivation_service,
    report_service,
)

_KK_CHARS = set("әғқңөұүһі")


async def _kk_assessment(db_session: AsyncSession, age_group: AgeGroup, age: int) -> Assessment:
    user = User(
        email=f"{uuid.uuid4()}@example.com", hashed_password="x",
        is_active=True, is_verified=True, locale="kk",
    )
    db_session.add(user)
    await db_session.flush()
    profile = Profile(
        user_id=user.id, name="Тест", age=age, grade=9,
        city="Алматы", country="Қазақстан", language="қазақша", age_group=age_group,
    )
    db_session.add(profile)
    await db_session.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db_session.add(assessment)
    await db_session.flush()
    return assessment


def _force_complete_llm_off(monkeypatch: pytest.MonkeyPatch, *, senior: bool) -> None:
    monkeypatch.setattr(assessment_shared, "likert_answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(assessment_shared, "likert_total_questions", AsyncMock(return_value=1))
    if senior:
        monkeypatch.setattr(motivation_service, "answered_count", AsyncMock(return_value=1))
        monkeypatch.setattr(motivation_service, "total_triplets", AsyncMock(return_value=1))
    else:
        monkeypatch.setattr(motivation_pair_service, "answered_count", AsyncMock(return_value=1))
        monkeypatch.setattr(motivation_pair_service, "total_pairs", AsyncMock(return_value=1))
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)


def _is_kk(text: str) -> bool:
    return bool(_KK_CHARS & set(text.lower()))


async def test_kk_owner_gets_a_kazakh_deterministic_report(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assessment = await _kk_assessment(db_session, AgeGroup.senior, 16)
    _force_complete_llm_off(monkeypatch, senior=True)

    response = await report_service.build_report(assessment.id, db_session)

    assert _is_kk(response.summary), response.summary
    assert _is_kk(response.final_analysis), response.final_analysis
    assert _is_kk(response.interest_map_note), response.interest_map_note
    assert _is_kk(response.personality_note), response.personality_note
    # every interest-map sphere label is Kazakh (riasec_labels() under kk)
    assert all(_is_kk(item.sphere) for item in response.interest_map)
    assert "Реалистичный" not in {item.sphere for item in response.interest_map}


async def test_kk_report_is_stable_on_cold_cache_reshape(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_report()/_shape_response recomputes the synthesis text — it must
    also honour the owner locale, not fall back to ru."""
    assessment = await _kk_assessment(db_session, AgeGroup.senior, 17)
    _force_complete_llm_off(monkeypatch, senior=True)

    await report_service.build_report(assessment.id, db_session)
    # cold cache: force the storage-reshape path
    monkeypatch.setattr(report_service, "_cache_get_response", AsyncMock(return_value=None))
    reshaped = await report_service.get_report(assessment.id, db_session)

    assert reshaped is not None
    assert _is_kk(reshaped.interest_map_note), reshaped.interest_map_note
    assert _is_kk(reshaped.personality_note), reshaped.personality_note
    assert all(_is_kk(item.sphere) for item in reshaped.interest_map)


async def test_ru_owner_report_is_unaffected(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x",
                is_active=True, is_verified=True)  # locale defaults to ru
    db_session.add(user)
    await db_session.flush()
    profile = Profile(user_id=user.id, name="Тест", age=16, grade=9, city="Алматы",
                      country="Казахстан", language="ru", age_group=AgeGroup.senior)
    db_session.add(profile)
    await db_session.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db_session.add(assessment)
    await db_session.flush()
    _force_complete_llm_off(monkeypatch, senior=True)

    response = await report_service.build_report(assessment.id, db_session)

    for text in (response.summary, response.final_analysis, response.interest_map_note,
                 response.personality_note):
        assert not (_KK_CHARS & set(text.lower())), text
    assert response.summary.startswith("По твоим ответам заметно")
    assert all(item.sphere in {
        "Реалистичный", "Исследовательский", "Артистичный",
        "Социальный", "Предприимчивый", "Конвенциональный",
    } for item in response.interest_map)


async def test_get_report_signals_locale_not_generated_vs_not_found(
    client, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """KZ-406: GET /result 404 distinguishes 'exists in another locale, needs
    lazy regen' (error_code) from 'no report at all'."""
    from app.services import auth_service

    # (a) never generated -> plain 404 "Report not found"
    assessment_a = await _kk_assessment(db_session, AgeGroup.senior, 16)
    profile_a = (await db_session.execute(
        select(Profile).where(Profile.id == assessment_a.profile_id)
    )).scalar_one()
    headers_a = {"Authorization": f"Bearer {auth_service.create_jwt_token(profile_a.user_id)}"}
    await db_session.commit()

    r = await client.get(f"/api/v1/result/{assessment_a.id}", headers=headers_a)
    assert r.status_code == 404
    body = r.json()
    assert body["detail"] == "Report not found"
    assert body.get("error_code") is None

    # (b) a ru row exists, owner is now kk -> 404 with the KZ-406 code
    assessment_b, user_b = await _senior_ru_then_kk(db_session, monkeypatch)
    headers_b = {"Authorization": f"Bearer {auth_service.create_jwt_token(user_b.id)}"}
    await db_session.commit()

    r = await client.get(f"/api/v1/result/{assessment_b.id}", headers=headers_b)
    assert r.status_code == 404
    assert r.json()["error_code"] == "report_locale_not_generated"


async def test_second_locale_translates_the_first_narrative_not_regenerates(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Variant A: once a report exists in one locale, the other locale is a
    one-call *translation* of it, not a fresh independent generation — so ru
    and kk say the same thing."""
    # 1. ru report first (LLM off -> deterministic ru narrative)
    assessment, user = await _senior_assessment_ru(db_session)
    _force_complete_llm_off(monkeypatch, senior=True)
    ru_report = await report_service.build_report(assessment.id, db_session)
    ru_row = (await db_session.execute(
        select(AnalysisResult).where(
            AnalysisResult.assessment_id == assessment.id, AnalysisResult.locale == "ru"
        )
    )).scalar_one()

    # 2. owner switches to kk; mock the LLM as a pure translator
    user.locale = "kk"
    await db_session.flush()
    for key in assessment_shared.report_cache_keys(assessment.id):
        await assessment_shared.get_redis().delete(key)

    translated = {
        "summary": "Сенің жауаптарың қазақ тілінде талданды: жаңа нәрсені зерттеуге, "
                   "жүйелі әрекет етуге және бастама көтеруге бейімсің. Осы қасиеттер "
                   "әртүрлі бағытта дамуға негіз болады. Нәтиже — қатаң үкім емес. "
                   "Оны бір жылда қайта қарауға болады.",
        "final_analysis": "Қызығушылықтарың мен ойлау стилің бір-бірін толықтырады. "
                          "Мотивацияң да сол бағытты нығайтады. Есепті бөлімдер осыны "
                          "біртұтас көрсетеді.",
        "strength_cards": [
            {"title": c["title"], "description": "Қазақша аударма: " + c["description"][:40]}
            for c in ru_row.strength_cards
        ],
        "thinking_style_notes": [
            {"title": n["title"], "description": "Қазақша аударма: " + n["description"][:40]}
            for n in ru_row.thinking_style_notes
        ],
    }
    complete_json = AsyncMock(return_value=translated)
    monkeypatch.setattr(llm_client, "is_enabled", lambda: True)
    monkeypatch.setattr(llm_client, "complete_json", complete_json)

    kk_report = await report_service.build_report(assessment.id, db_session)

    # exactly one LLM call — a translation, not the full generation pipeline
    assert complete_json.await_count == 1
    assert complete_json.await_args.args[2] == "report_narrative_translate"
    # the kk report carries the translated text, same card count as ru
    assert kk_report.summary == translated["summary"]
    assert kk_report.final_analysis == translated["final_analysis"]
    assert len(kk_report.strength_cards) == len(ru_report.strength_cards)
    # ru row untouched
    assert ru_row.summary == ru_report.summary


async def test_translation_works_kk_to_ru_and_rejects_a_kazakh_leak(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The translate path is symmetric: a kk-first report translates into ru
    on a switch. A translation that stays half-Kazakh is rejected and falls
    back to the deterministic ru narrative."""
    # kk report first (LLM off -> deterministic kk narrative)
    assessment, user = await _senior_assessment_ru(db_session)
    user.locale = "kk"
    await db_session.flush()
    _force_complete_llm_off(monkeypatch, senior=True)
    kk_report = await report_service.build_report(assessment.id, db_session)
    assert _is_kk(kk_report.summary)

    # switch to ru; first mock returns a BAD (still-Kazakh) translation
    user.locale = "ru"
    await db_session.flush()
    for key in assessment_shared.report_cache_keys(assessment.id):
        await assessment_shared.get_redis().delete(key)

    kk_row = (await db_session.execute(
        select(AnalysisResult).where(
            AnalysisResult.assessment_id == assessment.id, AnalysisResult.locale == "kk"
        )
    )).scalar_one()
    still_kazakh = {
        "summary": kk_row.summary,          # unchanged -> still Kazakh
        "final_analysis": kk_row.final_analysis,
        "strength_cards": [dict(c) for c in kk_row.strength_cards],
        "thinking_style_notes": [dict(n) for n in kk_row.thinking_style_notes],
    }
    monkeypatch.setattr(llm_client, "is_enabled", lambda: True)
    monkeypatch.setattr(llm_client, "complete_json", AsyncMock(return_value=still_kazakh))

    ru_report = await report_service.build_report(assessment.id, db_session)
    # rejected as a kk leak -> deterministic ru fallback, not the Kazakh text
    assert not _is_kk(ru_report.summary)
    assert ru_report.summary != kk_row.summary


async def _senior_ru_then_kk(db_session, monkeypatch):
    """A senior assessment with a `ru` AnalysisResult row whose owner is now kk."""
    from app.models.user import User as _User
    assessment, user = await _senior_assessment_ru(db_session)
    _force_complete_llm_off(monkeypatch, senior=True)
    await report_service.build_report(assessment.id, db_session)  # -> ru row
    user.locale = "kk"
    await db_session.flush()
    for key in assessment_shared.report_cache_keys(assessment.id):
        await assessment_shared.get_redis().delete(key)
    return assessment, user


async def _senior_assessment_ru(db_session):
    from app.models.user import User as _User
    user = _User(email=f"{uuid.uuid4()}@example.com", hashed_password="x",
                 is_active=True, is_verified=True)  # ru
    db_session.add(user)
    await db_session.flush()
    profile = Profile(user_id=user.id, name="Тест", age=16, grade=9, city="Алматы",
                      country="Казахстан", language="ru", age_group=AgeGroup.senior)
    db_session.add(profile)
    await db_session.flush()
    a = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db_session.add(a)
    await db_session.flush()
    return a, user
