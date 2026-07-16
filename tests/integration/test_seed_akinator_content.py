from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.akinator_question import AkinatorQuestion
from app.models.direction import Direction
from scripts.seed_akinator_content import (
    PROFESSION_AGE_GROUPS,
    PROFESSIONS,
    QUESTIONS,
    SECTIONS,
    seed_professions,
    seed_questions,
    seed_sections,
)


async def _run_full_seed(db: AsyncSession):
    section_ids, *section_counts = await seed_sections(db)
    prof_counts = await seed_professions(db, section_ids)
    q_counts = await seed_questions(db)
    return section_ids, tuple(section_counts), prof_counts, q_counts


async def test_seed_creates_expected_rows(db_session: AsyncSession):
    await _run_full_seed(db_session)

    section_slugs = [s["slug"] for s in SECTIONS]
    result = await db_session.execute(select(Direction).where(Direction.slug.in_(section_slugs)))
    sections = result.scalars().all()
    assert len(sections) == 16
    assert all(d.is_leaf is False for d in sections)

    profession_slugs = [p["slug"] for p in PROFESSIONS]
    result = await db_session.execute(select(Direction).where(Direction.slug.in_(profession_slugs)))
    professions = result.scalars().all()
    assert len(professions) == 67
    assert all(d.is_leaf is True for d in professions)
    assert all(d.parent_id is not None for d in professions)
    assert all(d.profile for d in professions)

    section_ids_by_slug = {s.slug: s.id for s in sections}
    for direction in professions:
        matching = next(p for p in PROFESSIONS if p["slug"] == direction.slug)
        assert direction.parent_id == section_ids_by_slug[matching["section"]]
        assert direction.profile == matching["profile"]
        # Calibration pass: all 67 professions are open to every age group
        # (previously defaulted to senior-only — junior/middle had no real
        # profiled professions to choose among at all).
        assert direction.age_groups == PROFESSION_AGE_GROUPS
        assert direction.label_junior == matching.get("label_junior")

    result = await db_session.execute(select(AkinatorQuestion).where(AkinatorQuestion.order.in_(range(len(QUESTIONS)))))
    questions = result.scalars().all()
    assert len(questions) == len(QUESTIONS)


async def test_rerun_creates_no_duplicates(db_session: AsyncSession):
    await _run_full_seed(db_session)
    _, _, (prof_inserted, prof_updated, prof_skipped), (q_inserted, q_updated, q_skipped) = (
        await _run_full_seed(db_session)
    )

    assert prof_inserted == 0
    assert q_inserted == 0
    assert prof_updated + prof_skipped == 67
    assert q_updated + q_skipped == len(QUESTIONS)

    profession_slugs = [p["slug"] for p in PROFESSIONS]
    result = await db_session.execute(select(Direction).where(Direction.slug.in_(profession_slugs)))
    assert len(result.scalars().all()) == 67

    result = await db_session.execute(select(AkinatorQuestion).where(AkinatorQuestion.order.in_(range(len(QUESTIONS)))))
    assert len(result.scalars().all()) == len(QUESTIONS)
