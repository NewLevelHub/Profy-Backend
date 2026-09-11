"""PRO-262 §7/§8: the two places where the admin could save something the
backend never checked.

A motivation triplet's three statements must carry three different
categories, and the "structure" of a program's grants was undocumented enough
that the admin edited it as raw JSON in a textarea
(docs/admin-backend-requests-pro-242.md §7, §8).
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.motivation import MotivationCategory, MotivationStatement
from app.models.program import Program
from app.models.university import University
from app.schemas.admin_content import AdminMotivationStatementUpdateRequest
from app.schemas.admin_university import AdminProgramGrant, AdminProgramUpdateRequest
from app.services import admin_content_service, admin_university_service
from app.services.admin_lock import AdminOverrideValidationError


async def _triplet(db: AsyncSession, index: int) -> list[MotivationStatement]:
    statements = [
        MotivationStatement(
            triplet_index=index, order=order, category=category, text=f"Утверждение {order}"
        )
        for order, category in enumerate(
            (MotivationCategory.interest, MotivationCategory.money, MotivationCategory.freedom)
        )
    ]
    db.add_all(statements)
    await db.commit()
    for statement in statements:
        await db.refresh(statement)
    return statements


# --- §7 triplet categories --------------------------------------------------


async def test_a_duplicate_category_inside_a_triplet_is_rejected(
    db_session: AsyncSession,
) -> None:
    """A duplicate silently breaks scoring: the (MOST, LEAST) pair stops
    identifying two distinct motives. Until now the only thing standing in the
    way was a line of UI text saying the backend would not check this."""
    first, second, _ = await _triplet(db_session, 900_300)

    with pytest.raises(AdminOverrideValidationError) as exc:
        await admin_content_service.update_motivation_statement(
            db_session,
            second.id,
            AdminMotivationStatementUpdateRequest(category=first.category),
        )

    assert "already used" in str(exc.value)
    assert str(first.order) in str(exc.value)


async def test_an_unused_category_is_accepted(db_session: AsyncSession) -> None:
    _, second, _ = await _triplet(db_session, 900_301)

    updated = await admin_content_service.update_motivation_statement(
        db_session,
        second.id,
        AdminMotivationStatementUpdateRequest(category=MotivationCategory.teamwork),
    )

    assert updated.category == MotivationCategory.teamwork


async def test_keeping_its_own_category_is_not_a_clash_with_itself(
    db_session: AsyncSession,
) -> None:
    _, second, _ = await _triplet(db_session, 900_302)

    updated = await admin_content_service.update_motivation_statement(
        db_session,
        second.id,
        AdminMotivationStatementUpdateRequest(category=second.category, text="Новый текст"),
    )

    assert updated.text == "Новый текст"


async def test_the_same_category_in_a_different_triplet_is_fine(
    db_session: AsyncSession,
) -> None:
    """The rule is per triplet — categories repeat across triplets by design,
    that is how the AG(2,3) generator covers every pair."""
    await _triplet(db_session, 900_303)
    _, other_second, _ = await _triplet(db_session, 900_304)

    updated = await admin_content_service.update_motivation_statement(
        db_session,
        other_second.id,
        AdminMotivationStatementUpdateRequest(category=MotivationCategory.stability),
    )

    assert updated.category == MotivationCategory.stability


# --- §8 grant structure -----------------------------------------------------


async def _program(db: AsyncSession, **kwargs) -> Program:
    university = University(name=f"Uni {uuid.uuid4()}", country="KZ", city="Almaty")
    db.add(university)
    await db.commit()
    program = Program(
        university_id=university.id, name=f"P {uuid.uuid4()}", language="ru", **kwargs
    )
    db.add(program)
    await db.commit()
    await db.refresh(program)
    return program


async def test_grants_are_validated_instead_of_being_free_form_json(
    db_session: AsyncSession,
) -> None:
    program = await _program(db_session)

    updated = await admin_university_service.update_program(
        db_session,
        program.id,
        AdminProgramUpdateRequest(
            grants=[AdminProgramGrant(name="Госгрант", amount="1 200 000 ₸")]
        ),
    )

    # Stored as plain dicts (JSONB-safe), and a field the caller never set is
    # not written as an explicit null.
    assert updated.grants == [{"name": "Госгрант", "amount": "1 200 000 ₸"}]


def test_a_grant_without_a_name_is_rejected() -> None:
    """The textarea accepted any JSON at all, so a structure nothing
    downstream could read saved cleanly."""
    with pytest.raises(Exception):
        AdminProgramGrant(amount="1 200 000 ₸")


def test_unknown_grant_keys_survive_a_round_trip() -> None:
    """A read-edit-write pass through the admin must not silently delete a
    field some importer added that this schema has not learned about yet."""
    grant = AdminProgramGrant(name="Грант", quota=30)

    assert grant.model_dump()["quota"] == 30


async def test_the_live_grant_shape_still_validates(db_session: AsyncSession) -> None:
    """Every one of the 1309 programs carrying grants today holds entries with
    `name` and nothing else — typing these must not invalidate the data that
    is already there."""
    program = await _program(db_session, grants=[{"name": "Ограниченные стипендии"}])

    grants = [AdminProgramGrant.model_validate(entry) for entry in program.grants]

    assert grants[0].name == "Ограниченные стипендии"
    assert grants[0].amount is None
