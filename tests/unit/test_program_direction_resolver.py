import pytest

from app.models.direction import Direction
from app.services.program_direction_resolver import program_direction_slugs_for


@pytest.mark.asyncio
async def test_program_direction_slugs_include_parent_section(db_session):
    # Fixture-only slugs (not real taxonomy slugs) — this test's own DB
    # transaction is rolled back on teardown, but real seeded content can
    # already be committed in a shared dev DB, so a real slug like
    # "akinator-it-data" would collide with it under a unique constraint.
    section = Direction(
        slug="test-section-it-data",
        name="IT и данные",
        description="section",
        is_leaf=False,
    )
    db_session.add(section)
    await db_session.flush()

    specialty = Direction(
        slug="test-specialty-software-engineer",
        name="Software Engineer",
        description="specialty",
        parent_id=section.id,
        is_leaf=True,
    )
    db_session.add(specialty)
    await db_session.flush()

    slugs = await program_direction_slugs_for("test-specialty-software-engineer", db_session)

    assert slugs == ["test-specialty-software-engineer", "test-section-it-data"]


@pytest.mark.asyncio
async def test_program_direction_slugs_fallback_to_leaf_only(db_session):
    slugs = await program_direction_slugs_for("unknown-specialty", db_session)

    assert slugs == ["unknown-specialty"]
