"""admin_locked_fields: a PATCH via admin_university_service must record which
top-level fields it touched, and the six seed/backfill scripts that overwrite-
if-different (not fill-if-empty) must skip any field already locked instead of
reverting a manual edit on the next deploy. See docs/admin-edit-lock-plan.md."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.program import Program
from app.models.university import University
from app.schemas.admin_university import AdminProgramUpdateRequest, AdminUniversityUpdateRequest
from app.services import admin_university_service
from app.services.admin_lock import is_locked, lock_fields


def test_lock_fields_merges_and_sorts() -> None:
    class _Row:
        admin_locked_fields: list[str] | None = None

    row = _Row()
    lock_fields(row, ["ranking"])
    lock_fields(row, ["city", "ranking"])

    assert row.admin_locked_fields == ["city", "ranking"]


def test_is_locked_false_for_empty_or_none() -> None:
    class _Row:
        admin_locked_fields = None

    assert is_locked(_Row(), "ranking") is False


async def test_update_university_locks_only_patched_fields(db_session: AsyncSession) -> None:
    university = University(name=f"Uni {uuid.uuid4()}", country="KZ", city="Almaty")
    db_session.add(university)
    await db_session.commit()
    await db_session.refresh(university)

    updated = await admin_university_service.update_university(
        db_session, university.id, AdminUniversityUpdateRequest(ranking=12)
    )

    assert updated.ranking == 12
    assert updated.admin_locked_fields == ["ranking"]
    assert is_locked(updated, "city") is False


async def test_update_program_locks_only_patched_fields(db_session: AsyncSession) -> None:
    university = University(name=f"Uni {uuid.uuid4()}", country="KZ", city="Almaty")
    db_session.add(university)
    await db_session.commit()
    await db_session.refresh(university)

    program = Program(
        university_id=university.id,
        name=f"Program {uuid.uuid4()}",
        language="Казахский, Русский",
        requirements={"notes": ["old"]},
    )
    db_session.add(program)
    await db_session.commit()
    await db_session.refresh(program)

    updated = await admin_university_service.update_program(
        db_session, program.id, AdminProgramUpdateRequest(requirements={"notes": ["admin note"]})
    )

    assert updated.requirements == {"notes": ["admin note"]}
    assert updated.admin_locked_fields == ["requirements"]
    assert is_locked(updated, "language") is False


async def test_backfill_ranking_from_label_skips_locked_field(
    db_session: AsyncSession, monkeypatch, capsys
) -> None:
    """backfill_ranking_from_label.py is NOT in cd.yml/cd-dev.yml (retired
    as a completed one-time migration — see its module docstring) — this
    covers its is_locked() guard for whenever someone runs it by hand again,
    not an automated production guarantee."""
    from scripts import backfill_ranking_from_label as script

    university = University(
        name=f"Uni {uuid.uuid4()}",
        country="KZ",
        city="Almaty",
        ranking_label="#701 (QS World University Rankings)",
        ranking=None,
    )
    db_session.add(university)
    await db_session.commit()
    await db_session.refresh(university)

    await admin_university_service.update_university(
        db_session, university.id, AdminUniversityUpdateRequest(ranking=5)
    )

    class _FakeSessionCtx:
        async def __aenter__(self_inner):
            return db_session

        async def __aexit__(self_inner, *exc):
            return False

    monkeypatch.setattr(script, "async_session", lambda: _FakeSessionCtx())
    monkeypatch.setattr(script.sys, "argv", ["backfill_ranking_from_label.py", "--apply"])

    await script.main()

    captured = capsys.readouterr()
    assert "admin-locked" in captured.out

    await db_session.refresh(university)
    assert university.ranking == 5  # not reverted to the label-parsed 701
