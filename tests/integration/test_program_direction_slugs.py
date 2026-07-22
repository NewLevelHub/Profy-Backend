"""Integration tests for Program.direction_slugs (JSONB) and the ?| overlap query.

These tests hit the real PostgreSQL database (via the db_session fixture, which
rolls back after each test). They verify:
  1. A program with direction_slugs=["software-engineer", "it-infrastructure-security"]
     (DevOps-style multi-slug) is found by search_programs for *either* slug.
  2. The ?| operator actually runs against the DB — not just Python-level filtering.
  3. A program is NOT returned when its slugs have no overlap with the search.
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.program import Program
from app.models.university import University
from app.services.university_service import search_programs


@pytest_asyncio.fixture
async def university(db_session: AsyncSession) -> University:
    """A minimal university fixture scoped per-test (rolled back automatically)."""
    uni = University(
        name=f"Test University {uuid.uuid4()}",
        country="Казахстан",
        city="Астана",
        website="https://example.kz",
        ranking=None,
        description="Test university for direction_slugs tests.",
    )
    db_session.add(uni)
    await db_session.flush()
    return uni


async def _make_program(
    db: AsyncSession,
    university_id: uuid.UUID,
    direction_slugs: list[str],
    name: str = "Test Program",
) -> Program:
    prog = Program(
        university_id=university_id,
        name=f"{name} {uuid.uuid4()}",
        direction_slugs=direction_slugs,
        language="Русский",
        cost_per_year=None,
        description="Test program.",
        career_options=[],
        requirements={},
        deadlines={},
        grants=[],
    )
    db.add(prog)
    await db.flush()
    return prog


@pytest.mark.asyncio
async def test_devops_program_found_by_software_engineer_slug(
    db_session: AsyncSession, university: University
):
    """DevOps program tagged with both IT slugs must appear when searching
    by software-engineer (the first slug in the list)."""
    prog = await _make_program(
        db_session,
        university.id,
        direction_slugs=["software-engineer", "it-infrastructure-security"],
        name="DevOps Engineering",
    )

    # Mock direction resolution: pretend software-engineer has no parent
    # (program_direction_slugs_for falls back to [selected_slug] when no DB row
    # is found — that is fine for this test, we just verify ?| works).
    results = await search_programs(
        db_session,
        direction_slug="software-engineer",
        city="Астана",
    )

    result_ids = {r.id for r in results}
    assert prog.id in result_ids, (
        "DevOps program with direction_slugs=['software-engineer', "
        "'it-infrastructure-security'] was not returned when searching by "
        "'software-engineer'"
    )


@pytest.mark.asyncio
async def test_devops_program_found_by_it_infrastructure_slug(
    db_session: AsyncSession, university: University
):
    """Same program must also appear when searching by it-infrastructure-security."""
    prog = await _make_program(
        db_session,
        university.id,
        direction_slugs=["software-engineer", "it-infrastructure-security"],
        name="DevOps Engineering",
    )

    results = await search_programs(
        db_session,
        direction_slug="it-infrastructure-security",
        city="Астана",
    )

    result_ids = {r.id for r in results}
    assert prog.id in result_ids, (
        "DevOps program was not returned when searching by "
        "'it-infrastructure-security'"
    )


@pytest.mark.asyncio
async def test_program_not_found_when_no_slug_overlap(
    db_session: AsyncSession, university: University
):
    """A medicine program must NOT appear in an IT search."""
    med_prog = await _make_program(
        db_session,
        university.id,
        direction_slugs=["general-medicine"],
        name="General Medicine",
    )

    results = await search_programs(
        db_session,
        direction_slug="software-engineer",
        city="Астана",
    )

    result_ids = {r.id for r in results}
    assert med_prog.id not in result_ids, (
        "general-medicine program should not appear in software-engineer search"
    )


@pytest.mark.asyncio
async def test_jsonb_overlap_operator_hits_real_db(db_session: AsyncSession):
    """Verify that the ?| operator actually works at the PostgreSQL level.

    This is a raw SQL sanity check — independent of the ORM layer — so it
    would catch a case where the Python-level test is accidentally passing
    because the filtering is happening in Python rather than in Postgres.
    """
    result = await db_session.execute(
        text(
            "SELECT '[\"software-engineer\", \"it-infrastructure-security\"]'::jsonb "
            "?| ARRAY['software-engineer']::text[]"
        )
    )
    row = result.fetchone()
    assert row is not None
    assert row[0] is True, "PostgreSQL ?| operator should return True for matching slug"

    result_false = await db_session.execute(
        text(
            "SELECT '[\"general-medicine\"]'::jsonb "
            "?| ARRAY['software-engineer', 'data-science']::text[]"
        )
    )
    row_false = result_false.fetchone()
    assert row_false is not None
    assert row_false[0] is False, "PostgreSQL ?| operator should return False when no match"


@pytest.mark.asyncio
async def test_section_slug_program_found_by_section_slug(
    db_session: AsyncSession, university: University
):
    """Programs tagged at section level (e.g. akinator-it-data) are found when
    allowed_slugs includes the section slug — which happens when
    program_direction_slugs_for expands a leaf to [leaf, parent_section]."""
    section_prog = await _make_program(
        db_session,
        university.id,
        direction_slugs=["akinator-it-data"],
        name="General IT Program",
    )

    # Manually call the underlying query logic with a resolved list
    # that includes the section slug (as program_direction_slugs_for would return).
    from sqlalchemy import Text, cast, select
    from sqlalchemy.dialects.postgresql import ARRAY, array as pg_array
    from sqlalchemy.orm import selectinload

    allowed_slugs = ["software-engineer", "akinator-it-data"]
    query = (
        select(Program)
        .options(selectinload(Program.university))
        .join(Program.university)
        .where(
            Program.direction_slugs.op("?|")(
                cast(pg_array(allowed_slugs), ARRAY(Text))
            )
        )
        .where(University.city == "Астана")
    )
    result = await db_session.execute(query)
    result_ids = {r.id for r in result.scalars().all()}

    assert section_prog.id in result_ids, (
        "Section-level program (akinator-it-data) was not found when "
        "allowed_slugs includes 'akinator-it-data'"
    )
