import pytest

from app.models.direction import Direction
from app.services.program_direction_resolver import program_direction_slugs_for


@pytest.mark.asyncio
async def test_program_direction_slugs_include_parent_section(db_session):
    section = Direction(
        slug="akinator-it-data",
        name="IT и данные",
        description="section",
        is_leaf=False,
    )
    db_session.add(section)
    await db_session.flush()

    profession = Direction(
        slug="programmer",
        name="Программист",
        description="profession",
        parent_id=section.id,
        is_leaf=True,
    )
    db_session.add(profession)
    await db_session.flush()

    slugs = await program_direction_slugs_for("programmer", db_session)

    assert slugs == ["programmer", "akinator-it-data"]


@pytest.mark.asyncio
async def test_program_direction_slugs_fallback_to_leaf_only(db_session):
    slugs = await program_direction_slugs_for("unknown-profession", db_session)

    assert slugs == ["unknown-profession"]
