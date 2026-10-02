"""Careers' «Почему тебе подходит» through the real report pipeline: stored
next to the careers (never inside them — the psychologist's careers PATCH
forbids extra keys), shared by every locale row, served on GET."""
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult, ReviewStatus
from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.i18n.catalog import tr
from app.schemas.psychologist_result import ReviewCareerPatch
from app.services import (
    assessment_shared,
    career_fit_service,
    llm_client,
    motivation_service,
    report_service,
)


async def _assessment(db_session: AsyncSession) -> tuple[Assessment, User]:
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x", is_active=True, is_verified=True)
    db_session.add(user)
    await db_session.flush()
    profile = Profile(
        user_id=user.id, name="Тест", age=16, grade=10, city="Алматы", country="Казахстан",
        language="ru", age_group=AgeGroup.senior,
        subjects_liked=["Информатика", "Математика", "Биология"], subjects_easy=["Химия"],
    )
    db_session.add(profile)
    await db_session.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db_session.add(assessment)
    await db_session.flush()
    return assessment, user


@pytest.fixture
def complete_llm_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assessment_shared, "likert_answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(assessment_shared, "likert_total_questions", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "total_triplets", AsyncMock(return_value=1))
    monkeypatch.setattr(assessment_shared, "belbin_and_astur_completed", AsyncMock(return_value=True))
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)


async def _rows(db_session: AsyncSession, assessment_id: uuid.UUID) -> dict[str, AnalysisResult]:
    rows = (
        await db_session.execute(select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id))
    ).scalars().all()
    return {row.locale: row for row in rows}


async def _drop_cache(assessment_id: uuid.UUID) -> None:
    for key in assessment_shared.report_cache_keys(assessment_id):
        await assessment_shared.get_redis().delete(key)


async def test_report_stores_career_fit_beside_the_careers(db_session: AsyncSession, complete_llm_off) -> None:
    assessment, _ = await _assessment(db_session)
    await report_service.build_report(assessment.id, db_session)
    row = (await _rows(db_session, assessment.id))["ru"]

    assert career_fit_service.is_current(row.career_fit)
    assert set(row.career_fit["careers"]) == {c["slug"] for c in row.careers}
    # The stored career dicts stay exactly what the psychologist's careers
    # PATCH accepts (extra="forbid") — an editor round-trip must never 422.
    for career in row.careers:
        ReviewCareerPatch.model_validate(career)


async def test_get_serves_why_and_the_reasons(db_session: AsyncSession, complete_llm_off) -> None:
    assessment, _ = await _assessment(db_session)
    await report_service.build_report(assessment.id, db_session)
    row = (await _rows(db_session, assessment.id))["ru"]
    row.review_status = ReviewStatus.published
    await db_session.flush()
    await _drop_cache(assessment.id)

    report = await report_service.get_report(assessment.id, db_session)
    assert all(c.why for c in report.careers)
    subjects = [r for c in report.careers for r in c.fit_reasons if r.kind == "subject"]
    assert subjects, "a liked/easy school subject the profession needs must surface"
    assert all("«" in r.text and r.fact in r.text for r in subjects)
    for career in report.careers:
        assert all(key for key in career.fit_keys)
    await _drop_cache(assessment.id)


async def test_a_second_locale_row_shares_the_same_career_fit(
    db_session: AsyncSession, complete_llm_off
) -> None:
    assessment, user = await _assessment(db_session)
    await report_service.build_report(assessment.id, db_session)
    user.locale = "kk"
    await db_session.flush()
    await _drop_cache(assessment.id)

    kk_report = await report_service.build_report(assessment.id, db_session)
    rows = await _rows(db_session, assessment.id)
    assert rows["kk"].career_fit == rows["ru"].career_fit
    texts = [r.text for c in kk_report.careers for r in c.fit_reasons]
    assert texts and all("пән" in t or "мамандықта" in t for t in texts)
    await _drop_cache(assessment.id)


async def test_a_report_without_career_fit_still_renders(db_session: AsyncSession, complete_llm_off) -> None:
    assessment, _ = await _assessment(db_session)
    await report_service.build_report(assessment.id, db_session)
    row = (await _rows(db_session, assessment.id))["ru"]
    row.career_fit = None
    row.review_status = ReviewStatus.published
    await db_session.flush()
    await _drop_cache(assessment.id)

    report = await report_service.get_report(assessment.id, db_session)
    assert report.careers and all(c.why and not c.fit_reasons for c in report.careers)
    assert all("пока недостаточно данных" in c.why for c in report.careers)
    await _drop_cache(assessment.id)
