"""PRO-262 §4: an admin edit must be undoable.

A PATCH on question-bank content records an override, and every seed script
composes overrides back over the bank on each deploy — so before this, one
mistyped character pinned a field forever and the only way out was editing the
row in the database by hand (docs/admin-backend-requests-pro-242.md §4).
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.direction import Direction
from app.models.motivation import MotivationCategory, MotivationStatement
from app.models.profile import AgeGroup
from app.models.program import Program
from app.models.question import Question, QuestionInstrument
from app.models.university import University
from app.schemas.admin_content import (
    AdminDirectionUpdateRequest,
    AdminMotivationStatementUpdateRequest,
    AdminQuestionUpdateRequest,
)
from app.schemas.admin_university import AdminUniversityUpdateRequest
from app.services import admin_content_service, admin_university_service
from app.services.admin_lock import clear_overrides, is_locked, sync_fields, unlock_fields


async def _question(db: AsyncSession, text: str) -> Question:
    question = Question(
        instrument=QuestionInstrument.riasec, text=text, order=0, age_tier=AgeGroup.senior
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)
    return question


# --- the override round trip ------------------------------------------------


async def test_patch_records_what_it_replaced(db_session: AsyncSession) -> None:
    question = await _question(db_session, "Текст из банка")

    updated = await admin_content_service.update_question(
        db_session, question.id, AdminQuestionUpdateRequest(text="Правка админа")
    )

    assert updated.text == "Правка админа"
    assert updated.overrides["text"] == {
        "value": "Правка админа",
        "bank_value": "Текст из банка",
    }


async def test_clearing_one_override_restores_the_bank_value_immediately(
    db_session: AsyncSession,
) -> None:
    """"Immediately" is the point: dropping the override alone would leave the
    admin's text on the row until the next deploy re-ran the seed script."""
    question = await _question(db_session, "Текст из банка")
    await admin_content_service.update_question(
        db_session, question.id, AdminQuestionUpdateRequest(text="Правка", icon="🙂")
    )

    reverted = await admin_content_service.clear_question_overrides(
        db_session, question.id, "text"
    )

    assert reverted.text == "Текст из банка"
    assert "text" not in reverted.overrides
    assert reverted.icon == "🙂"  # the other edit is untouched
    assert "icon" in reverted.overrides


async def test_clearing_all_overrides_puts_the_whole_row_back(
    db_session: AsyncSession,
) -> None:
    question = await _question(db_session, "Текст из банка")
    await admin_content_service.update_question(
        db_session, question.id, AdminQuestionUpdateRequest(text="Правка", icon="🙂")
    )

    reverted = await admin_content_service.clear_question_overrides(db_session, question.id)

    assert reverted.text == "Текст из банка"
    assert reverted.icon is None
    assert reverted.overrides == {}


async def test_re_editing_keeps_the_original_bank_value(db_session: AsyncSession) -> None:
    """The second edit replaces the first edit, not the bank — recording the
    first edit as the "original" would make revert restore an admin's typo."""
    question = await _question(db_session, "Текст из банка")
    await admin_content_service.update_question(
        db_session, question.id, AdminQuestionUpdateRequest(text="Первая правка")
    )
    await admin_content_service.update_question(
        db_session, question.id, AdminQuestionUpdateRequest(text="Вторая правка")
    )

    reverted = await admin_content_service.clear_question_overrides(db_session, question.id)

    assert reverted.text == "Текст из банка"


async def test_clearing_a_field_that_is_not_overridden_is_reported(
    db_session: AsyncSession,
) -> None:
    question = await _question(db_session, "Текст из банка")

    with pytest.raises(ValueError, match="not overridden"):
        await admin_content_service.clear_question_overrides(db_session, question.id, "text")


# --- interaction with the seed resync ---------------------------------------


async def test_a_resync_still_keeps_the_override_and_refreshes_the_bank_value(
    db_session: AsyncSession,
) -> None:
    """What a deploy does: sync_fields() must leave the admin's value in place
    while following the bank's own rewording, so a later revert restores the
    wording the bank uses *now*, not the one it used when the edit was made."""
    question = await _question(db_session, "Старый текст банка")
    await admin_content_service.update_question(
        db_session, question.id, AdminQuestionUpdateRequest(text="Правка админа")
    )
    await db_session.refresh(question)

    sync_fields(question, {"text": "Новый текст банка"})

    assert question.text == "Правка админа"
    assert question.overrides["text"]["bank_value"] == "Новый текст банка"

    clear_overrides(question)
    assert question.text == "Новый текст банка"


async def test_an_override_written_before_bank_values_were_recorded_still_clears(
    db_session: AsyncSession,
) -> None:
    """Rows migrated from the flat shape carry no bank_value key at all, which
    is what "unknown" means — the revert drops the override and leaves the next
    seed run to restore the value."""
    question = await _question(db_session, "Значение админа")
    question.overrides = {"text": {"value": "Значение админа"}}
    await db_session.commit()

    reverted = await admin_content_service.clear_question_overrides(db_session, question.id)

    assert reverted.overrides == {}
    assert reverted.text == "Значение админа"


async def test_a_null_bank_value_is_restored_not_treated_as_unknown(
    db_session: AsyncSession,
) -> None:
    """icon/short_text/frame are nullable, so "the bank had nothing here" is a
    real value to put back — encoding "unknown" as null would make every such
    field un-revertable."""
    question = await _question(db_session, "Текст")
    assert question.icon is None

    await admin_content_service.update_question(
        db_session, question.id, AdminQuestionUpdateRequest(icon="🙂")
    )
    reverted = await admin_content_service.clear_question_overrides(db_session, question.id)

    assert reverted.icon is None


async def test_legacy_flat_override_is_still_readable(db_session: AsyncSession) -> None:
    """A seed run can meet a database that has not been migrated yet."""
    question = await _question(db_session, "Значение админа")
    question.overrides = {"text": "Значение админа"}
    await db_session.commit()

    sync_fields(question, {"text": "Текст банка"})

    assert question.text == "Значение админа"


# --- the other content types ------------------------------------------------


async def test_direction_and_motivation_overrides_clear_too(
    db_session: AsyncSession,
) -> None:
    direction = Direction(
        name="Из банка", slug=f"dir-{uuid.uuid4()}", holland_code="RIS"
    )
    statement = MotivationStatement(
        triplet_index=900_200, order=0, category=MotivationCategory.interest, text="Из банка"
    )
    db_session.add_all([direction, statement])
    await db_session.commit()

    await admin_content_service.update_direction(
        db_session, direction.id, AdminDirectionUpdateRequest(name="Правка")
    )
    await admin_content_service.update_motivation_statement(
        db_session, statement.id, AdminMotivationStatementUpdateRequest(text="Правка")
    )

    reverted_direction = await admin_content_service.clear_direction_overrides(
        db_session, direction.id
    )
    reverted_statement = await admin_content_service.clear_motivation_statement_overrides(
        db_session, statement.id
    )

    assert reverted_direction.name == "Из банка"
    assert reverted_statement.text == "Из банка"


# --- university/program locks ----------------------------------------------


async def test_unlocking_a_university_field_returns_it_to_seed_control(
    db_session: AsyncSession,
) -> None:
    """A lock stores only the field's name, so unlocking restores nothing by
    itself — the value stays until a seed run overwrites it, which it now may."""
    university = University(name=f"Uni {uuid.uuid4()}", country="KZ", city="Almaty")
    db_session.add(university)
    await db_session.commit()

    await admin_university_service.update_university(
        db_session, university.id, AdminUniversityUpdateRequest(ranking=12, city="Астана")
    )

    unlocked = await admin_university_service.unlock_university_fields(
        db_session, university.id, "ranking"
    )

    assert is_locked(unlocked, "ranking") is False
    assert is_locked(unlocked, "city") is True
    assert unlocked.ranking == 12  # the value itself was never recorded anywhere

    fully_unlocked = await admin_university_service.unlock_university_fields(
        db_session, university.id
    )
    assert fully_unlocked.admin_locked_fields == []


async def test_unlocking_a_field_that_is_not_locked_is_reported(
    db_session: AsyncSession,
) -> None:
    university = University(name=f"Uni {uuid.uuid4()}", country="KZ", city="Almaty")
    db_session.add(university)
    await db_session.commit()

    with pytest.raises(ValueError, match="not locked"):
        await admin_university_service.unlock_university_fields(
            db_session, university.id, "ranking"
        )


async def test_unlock_fields_helper_removes_only_what_was_asked(db_session: AsyncSession) -> None:
    class _Row:
        admin_locked_fields = ["city", "ranking", "website"]

    row = _Row()
    removed = unlock_fields(row, ["ranking", "not-locked"])

    assert removed == ["ranking"]
    assert row.admin_locked_fields == ["city", "website"]


async def test_program_locks_clear_as_well(db_session: AsyncSession) -> None:
    university = University(name=f"Uni {uuid.uuid4()}", country="KZ", city="Almaty")
    db_session.add(university)
    await db_session.commit()
    program = Program(university_id=university.id, name=f"P {uuid.uuid4()}", language="ru")
    db_session.add(program)
    await db_session.commit()

    from app.schemas.admin_university import AdminProgramUpdateRequest

    await admin_university_service.update_program(
        db_session, program.id, AdminProgramUpdateRequest(language="Английский")
    )

    unlocked = await admin_university_service.unlock_program_fields(db_session, program.id)

    assert unlocked.admin_locked_fields == []
