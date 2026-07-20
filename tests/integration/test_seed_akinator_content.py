from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.akinator_question import AkinatorQuestion
from app.models.direction import Direction
from scripts.seed_akinator_content import (
    QUESTIONS,
    SECTIONS,
    SPECIALTIES,
    SPECIALTY_AGE_GROUPS,
    seed_questions,
    seed_sections,
    seed_specialties,
)


async def _run_full_seed(db: AsyncSession):
    section_ids, *section_counts = await seed_sections(db)
    spec_counts = await seed_specialties(db, section_ids)
    q_counts = await seed_questions(db)
    return section_ids, tuple(section_counts), spec_counts, q_counts


async def test_seed_creates_expected_rows(db_session: AsyncSession):
    await _run_full_seed(db_session)

    section_slugs = [s["slug"] for s in SECTIONS]
    result = await db_session.execute(select(Direction).where(Direction.slug.in_(section_slugs)))
    sections = result.scalars().all()
    assert len(sections) == 13
    assert all(d.is_leaf is False for d in sections)

    specialty_slugs = [p["slug"] for p in SPECIALTIES]
    result = await db_session.execute(select(Direction).where(Direction.slug.in_(specialty_slugs)))
    specialties = result.scalars().all()
    assert len(specialties) == 38
    assert all(d.is_leaf is True for d in specialties)
    assert all(d.parent_id is not None for d in specialties)
    assert all(d.profile for d in specialties)

    section_ids_by_slug = {s.slug: s.id for s in sections}
    for direction in specialties:
        matching = next(p for p in SPECIALTIES if p["slug"] == direction.slug)
        assert direction.parent_id == section_ids_by_slug[matching["section"]]
        assert direction.profile == matching["profile"]
        # Specialty pivot: `professions` is what the client shows under the
        # matched specialty (e.g. Software Engineer -> Backend/Frontend/QA).
        assert direction.professions == matching["professions"]
        # Age-group pass: specialties (leaves) are only offered to middle/senior —
        # junior converges to the broader section instead.
        assert direction.age_groups == SPECIALTY_AGE_GROUPS
        assert direction.label_junior == matching.get("label_junior")

    result = await db_session.execute(select(AkinatorQuestion).where(AkinatorQuestion.order.in_([q["order"] for q in QUESTIONS])))
    questions = result.scalars().all()
    assert len(questions) == len(QUESTIONS)


async def test_rerun_creates_no_duplicates(db_session: AsyncSession):
    await _run_full_seed(db_session)
    _, _, (spec_inserted, spec_updated, spec_skipped), (q_inserted, q_updated, q_skipped) = (
        await _run_full_seed(db_session)
    )

    assert spec_inserted == 0
    assert q_inserted == 0
    assert spec_updated + spec_skipped == 38
    assert q_updated + q_skipped == len(QUESTIONS)

    specialty_slugs = [p["slug"] for p in SPECIALTIES]
    result = await db_session.execute(select(Direction).where(Direction.slug.in_(specialty_slugs)))
    assert len(result.scalars().all()) == 38

    result = await db_session.execute(select(AkinatorQuestion).where(AkinatorQuestion.order.in_([q["order"] for q in QUESTIONS])))
    assert len(result.scalars().all()) == len(QUESTIONS)
