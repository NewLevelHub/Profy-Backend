"""Admin editing of localized bank-seeded content — single-row redesign.

`questions`/`question_pairs`/`motivation_statements`/`directions` used to carry one physical row per locale (KZ-301), so an admin
editing "the" question picked one language's row and the other was a
separate, independently-editable row. That's gone — one row now holds both
`{"ru": ..., "kk": ...}` values for a localized field (docs/i18n-contract.md
§8). This covers the resulting contract:

- List items no longer report a `locale` (there's only one row) and show the
  `ru` text (the admin panel itself stays `ru`-only, i18n-contract §2).
- Detail responses expose the full `{"ru": ..., "kk": ...}` map for every
  localized field, so both languages are visible in one place.
- PATCHing a localized field requires an explicit `locale` — which language
  is being edited — and only that language's value changes; the other
  locale's value, and the override record backing it, are untouched.
- PATCHing a non-localized (structural) field needs no `locale`.

Real transactional Postgres session (rolled back) — real seeded content, no
synthetic rows needed for the read-only checks.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.direction import Direction
from app.models.motivation import MotivationStatement
from app.models.question import Question, QuestionInstrument
from app.models.question_pair import QuestionPair
from app.schemas.admin_content import (
    AdminDirectionUpdateRequest,
    AdminMotivationStatementUpdateRequest,
    AdminQuestionPairUpdateRequest,
    AdminQuestionUpdateRequest,
)
from app.services import admin_content_service
from app.services.admin_lock import AdminOverrideValidationError


async def _first(db_session: AsyncSession, model, **filters):
    stmt = select(model)
    for key, value in filters.items():
        stmt = stmt.where(getattr(model, key) == value)
    row = (await db_session.execute(stmt.limit(1))).scalar_one_or_none()
    assert row is not None, f"no seeded {model.__tablename__} row to test against"
    return row


async def test_question_list_items_show_ru_text_with_no_locale_field(db_session: AsyncSession) -> None:
    page = await admin_content_service.list_questions(db_session, limit=5)
    assert page.items
    for item in page.items:
        assert not hasattr(item, "locale")
        assert item.text  # resolved ru string, not a {"ru": ...} dict


async def test_question_detail_exposes_both_locales(db_session: AsyncSession) -> None:
    q = await _first(db_session, Question, instrument=QuestionInstrument.riasec)
    detail = await admin_content_service.get_question_detail(db_session, q.id)
    assert set(detail.text) >= {"ru", "kk"}


async def test_question_patch_without_locale_is_rejected_for_a_localized_field(
    db_session: AsyncSession,
) -> None:
    q = await _first(db_session, Question, instrument=QuestionInstrument.riasec)
    with pytest.raises(AdminOverrideValidationError):
        await admin_content_service.update_question(
            db_session, q.id, AdminQuestionUpdateRequest(text="Новый текст")
        )


async def test_question_patch_edits_only_the_given_locale(db_session: AsyncSession) -> None:
    q = await _first(db_session, Question, instrument=QuestionInstrument.riasec)
    original_ru = q.text["ru"]

    updated = await admin_content_service.update_question(
        db_session, q.id, AdminQuestionUpdateRequest(text="Жаңа мәтін", locale="kk")
    )

    assert updated.text["kk"] == "Жаңа мәтін"
    assert updated.text["ru"] == original_ru  # untouched
    # Structured {value, bank_value} entry (admin-lock's revert feature) —
    # `value` is the per-locale override map, `bank_value` the full map the
    # bank had before this first edit on the field.
    assert updated.overrides["text"]["value"] == {"kk": "Жаңа мәтін"}
    assert updated.overrides["text"]["bank_value"]["ru"] == original_ru


async def test_question_patch_structural_field_needs_no_locale(db_session: AsyncSession) -> None:
    q = await _first(db_session, Question, instrument=QuestionInstrument.big_five)
    from app.models.question import Keyed

    other = Keyed.minus if q.keyed == Keyed.plus else Keyed.plus
    updated = await admin_content_service.update_question(
        db_session, q.id, AdminQuestionUpdateRequest(keyed=other)
    )
    assert updated.keyed == other
    # Structured {value, bank_value} entry (admin-lock's revert feature).
    assert updated.overrides["keyed"]["value"] == other.value


async def test_question_pair_patch_edits_only_the_given_locale(db_session: AsyncSession) -> None:
    p = await _first(db_session, QuestionPair)
    updated = await admin_content_service.update_question_pair(
        db_session, p.id, AdminQuestionPairUpdateRequest(option_a_text="Жаңа нұсқа", locale="kk")
    )
    assert updated.option_a_text["kk"] == "Жаңа нұсқа"


async def test_motivation_statement_patch_edits_only_the_given_locale(db_session: AsyncSession) -> None:
    s = await _first(db_session, MotivationStatement)
    original_ru = s.text["ru"]
    updated = await admin_content_service.update_motivation_statement(
        db_session, s.id, AdminMotivationStatementUpdateRequest(text="Жаңа мәтін", locale="kk")
    )
    assert updated.text["kk"] == "Жаңа мәтін"
    assert updated.text["ru"] == original_ru


async def test_direction_detail_exposes_both_locales_for_every_content_field(
    db_session: AsyncSession,
) -> None:
    d = await _first(db_session, Direction)
    detail = await admin_content_service.get_direction_detail(db_session, d.id)
    assert set(detail.name) >= {"ru", "kk"}
    assert "ru" in detail.description


async def test_direction_patch_edits_only_the_given_locale(db_session: AsyncSession) -> None:
    d = await _first(db_session, Direction)
    original_ru = d.name["ru"]
    updated = await admin_content_service.update_direction(
        db_session, d.id, AdminDirectionUpdateRequest(name="Жаңа атау", locale="kk")
    )
    assert updated.name["kk"] == "Жаңа атау"
    assert updated.name["ru"] == original_ru


async def test_direction_patch_structural_field_needs_no_locale(db_session: AsyncSession) -> None:
    d = await _first(db_session, Direction)
    updated = await admin_content_service.update_direction(
        db_session, d.id, AdminDirectionUpdateRequest(holland_code="XYZ")
    )
    assert updated.holland_code == "XYZ"
