"""KZ-301 — `locale` column on the bank-seeded content tables.

Covers: existing content is `ru`; display reads resolve the request locale and
fall back to the whole `ru` set (recording a fallback) when the locale has no
rows; a translated locale's rows win when they exist; scoring denominators stay
pinned to `ru`; and structural fields match between `ru` and any other locale
for the same logical row.

Real transactional Postgres session (rolled back) — synthetic `kk` rows added
in a test never escape it.
"""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import i18n
from app.models.direction import Direction
from app.models.motivation import MotivationStatement
from app.models.motivation_pair import MotivationPair
from app.models.profile import AgeGroup
from app.models.question import Question, QuestionInstrument
from app.models.question_pair import QuestionPair
from app.services import assessment_shared, question_service, riasec_service
from app.services.content_locale import localized_rows

_CONTENT_MODELS = [Question, QuestionPair, MotivationStatement, MotivationPair, Direction]

# (model, natural-key attribute names, structural attribute names that must be
# byte-identical between locales of one logical row)
_STRUCTURAL: list[tuple[type, tuple[str, ...], tuple[str, ...]]] = [
    (
        Question,
        ("order",),
        ("instrument", "riasec_type", "bigfive_domain", "mi_category", "facet", "keyed", "age_tier"),
    ),
    (QuestionPair, ("instrument", "pair_index"), ("age_tier",)),
    (MotivationStatement, ("triplet_index", "order"), ("category",)),
    (MotivationPair, ("pair_index",), ("category_a", "category_b")),
    (Direction, ("slug",), ("holland_code",)),
]


@pytest.fixture(autouse=True)
def _clear_fallback_counts():
    i18n.reset_fallback_counts()
    yield
    i18n.reset_fallback_counts()


async def test_existing_content_is_all_ru(db_session: AsyncSession) -> None:
    for model in _CONTENT_MODELS:
        non_ru = await db_session.execute(
            select(func.count()).select_from(model).where(model.locale != "ru")
        )
        assert non_ru.scalar_one() == 0, f"{model.__tablename__} has non-ru rows pre-translation"
        total = await db_session.execute(select(func.count()).select_from(model))
        assert total.scalar_one() > 0


async def test_localized_rows_falls_back_to_full_ru_set_and_records_it(
    db_session: AsyncSession,
) -> None:
    i18n._current_locale.set("kk")

    rows = await localized_rows(db_session, select(Direction), Direction.locale)

    assert rows, "fallback must return the ru set, not empty"
    assert all(d.locale == "ru" for d in rows)
    assert i18n.fallback_counts().get("kk") == 1


async def test_localized_rows_prefers_the_requested_locale_when_present(
    db_session: AsyncSession,
) -> None:
    ru = (
        await db_session.execute(select(Direction).where(Direction.locale == "ru").limit(1))
    ).scalar_one()
    db_session.add(
        Direction(
            locale="kk",
            name=f"{ru.name} (kk)",
            slug=ru.slug,
            holland_code=ru.holland_code,
        )
    )
    await db_session.flush()
    i18n._current_locale.set("kk")

    rows = await localized_rows(
        db_session, select(Direction).where(Direction.slug == ru.slug), Direction.locale
    )

    assert [d.locale for d in rows] == ["kk"]
    assert i18n.fallback_counts().get("kk") is None


async def test_get_all_questions_kk_falls_back_to_the_whole_ru_set(
    db_session: AsyncSession,
) -> None:
    ru_senior = (
        await db_session.execute(
            select(func.count())
            .select_from(Question)
            .where(Question.age_tier.in_(("junior", "middle", "senior")), Question.locale == "ru")
        )
    ).scalar_one()
    i18n._current_locale.set("kk")

    questions = await question_service.get_all_questions(db_session, AgeGroup.senior)

    assert len(questions) == ru_senior
    assert i18n.fallback_counts().get("kk") == 1


async def test_scoring_denominators_ignore_kk_rows(db_session: AsyncSession) -> None:
    """A `kk` clone of every senior RIASEC question must not change the counts
    that normalization divides by — they pin to `ru`."""
    ru_questions = (
        await db_session.execute(
            select(Question).where(
                Question.instrument == QuestionInstrument.riasec, Question.locale == "ru"
            )
        )
    ).scalars().all()
    before_riasec = await riasec_service.question_counts(db_session, AgeGroup.senior)
    before_likert = await assessment_shared.likert_total_questions(db_session, AgeGroup.senior)

    for q in ru_questions:
        db_session.add(
            Question(
                locale="kk",
                instrument=q.instrument,
                riasec_type=q.riasec_type,
                bigfive_domain=q.bigfive_domain,
                mi_category=q.mi_category,
                facet=q.facet,
                keyed=q.keyed,
                text=f"{q.text} (kk)",
                short_text=q.short_text,
                icon=q.icon,
                order=q.order,
                age_tier=q.age_tier,
            )
        )
    await db_session.flush()

    assert await riasec_service.question_counts(db_session, AgeGroup.senior) == before_riasec
    assert await assessment_shared.likert_total_questions(db_session, AgeGroup.senior) == before_likert


async def test_structural_fields_match_between_ru_and_other_locales(
    db_session: AsyncSession,
) -> None:
    """The DB is `ru`-only today, so this passes vacuously — but it is the
    guard KZ-302..306 rely on: adding a `kk` row whose scoring/order fields
    drift from its `ru` sibling fails here."""
    for model, key_attrs, struct_attrs in _STRUCTURAL:
        rows = (await db_session.execute(select(model))).scalars().all()
        ru_by_key = {
            tuple(getattr(r, a) for a in key_attrs): r for r in rows if r.locale == "ru"
        }
        for row in rows:
            if row.locale == "ru":
                continue
            key = tuple(getattr(row, a) for a in key_attrs)
            sibling = ru_by_key.get(key)
            assert sibling is not None, f"{model.__tablename__} {key} has no ru sibling"
            for attr in struct_attrs:
                assert getattr(row, attr) == getattr(sibling, attr), (
                    f"{model.__tablename__} {key}: {attr} differs between "
                    f"{row.locale} and ru"
                )
