"""KZ-301 / KZ-302 — `locale` on the bank-seeded content tables.

Covers: tables with no translation yet stay `ru`-only; the RIASEC question bank
now carries `kk` (KZ-302); `localized_rows` resolves the request locale
per natural key and falls back to `ru` for units the locale hasn't translated
(recording a fallback); scoring denominators stay pinned to `ru`; and structural
fields match between `ru` and every other locale of one logical row.

Real transactional Postgres session (rolled back) — synthetic rows added in a
test never escape it.
"""

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

# Tables not translated by any ticket up to KZ-302.
_UNTRANSLATED_MODELS = [QuestionPair, MotivationStatement, MotivationPair, Direction]

# (model, natural-key attrs, structural attrs that must be identical across a
# logical row's locales)
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


async def test_untranslated_tables_are_still_ru_only(db_session: AsyncSession) -> None:
    for model in _UNTRANSLATED_MODELS:
        non_ru = await db_session.execute(
            select(func.count()).select_from(model).where(model.locale != "ru")
        )
        assert non_ru.scalar_one() == 0, f"{model.__tablename__} has unexpected non-ru rows"
        total = await db_session.execute(select(func.count()).select_from(model))
        assert total.scalar_one() > 0


async def test_riasec_bank_has_a_complete_kk_set(db_session: AsyncSession) -> None:
    """KZ-302: every RIASEC question has a `kk` row, structurally identical to
    its `ru` sibling, with genuinely different text."""
    rows = (
        await db_session.execute(
            select(Question).where(Question.instrument == QuestionInstrument.riasec)
        )
    ).scalars().all()
    ru = {q.order: q for q in rows if q.locale == "ru"}
    kk = {q.order: q for q in rows if q.locale == "kk"}

    assert set(kk) == set(ru) and len(kk) == 146
    for order, kk_q in kk.items():
        ru_q = ru[order]
        assert kk_q.riasec_type == ru_q.riasec_type
        assert kk_q.age_tier == ru_q.age_tier
        assert kk_q.icon == ru_q.icon
        assert (kk_q.short_text is None) == (ru_q.short_text is None)
        assert kk_q.text and kk_q.text != ru_q.text


async def test_localized_rows_falls_back_per_key_and_records_it(
    db_session: AsyncSession,
) -> None:
    """`directions` has no `kk` yet — every unit falls back, once."""
    i18n._current_locale.set("kk")

    rows = await localized_rows(db_session, select(Direction), Direction, key="slug")

    assert rows and all(d.locale == "ru" for d in rows)
    assert i18n.fallback_counts().get("kk") == 1


async def test_localized_rows_swaps_in_only_the_translated_unit(
    db_session: AsyncSession,
) -> None:
    ru = (
        await db_session.execute(select(Direction).where(Direction.locale == "ru").limit(1))
    ).scalar_one()
    db_session.add(
        Direction(locale="kk", name=f"{ru.name} (kk)", slug=ru.slug, holland_code=ru.holland_code)
    )
    await db_session.flush()
    i18n._current_locale.set("kk")

    rows = await localized_rows(db_session, select(Direction), Direction, key="slug")

    by_slug = {d.slug: d for d in rows}
    assert by_slug[ru.slug].locale == "kk"
    assert all(d.locale == "ru" for d in rows if d.slug != ru.slug)
    # other directions still untranslated -> a fallback was recorded
    assert i18n.fallback_counts().get("kk") == 1


async def test_localized_rows_no_fallback_when_locale_is_complete(
    db_session: AsyncSession,
) -> None:
    i18n._current_locale.set("kk")

    rows = await localized_rows(
        db_session,
        select(Question).where(Question.instrument == QuestionInstrument.riasec),
        Question,
        key="order",
    )

    assert len(rows) == 146 and all(q.locale == "kk" for q in rows)
    assert i18n.fallback_counts().get("kk") is None


async def test_get_all_questions_kk_serves_translated_riasec_and_ru_for_the_rest(
    db_session: AsyncSession,
) -> None:
    ru_senior = (
        await db_session.execute(
            select(func.count())
            .select_from(Question)
            .where(Question.age_tier.in_(("junior", "middle", "senior")), Question.locale == "ru")
        )
    ).scalar_one()
    ru_riasec_text = {
        r.text
        for r in (
            await db_session.execute(
                select(Question).where(
                    Question.instrument == QuestionInstrument.riasec, Question.locale == "ru"
                )
            )
        ).scalars()
    }
    i18n._current_locale.set("kk")

    questions = await question_service.get_all_questions(db_session, AgeGroup.senior)

    assert len(questions) == ru_senior  # never a short set
    riasec = [q for q in questions if q.instrument == QuestionInstrument.riasec]
    others = [q for q in questions if q.instrument != QuestionInstrument.riasec]
    assert riasec and all(q.text not in ru_riasec_text for q in riasec)  # kk text
    assert others and all(q.text for q in others)  # ru text, still present
    assert i18n.fallback_counts().get("kk") == 1  # big_five + mi not translated yet


async def test_scoring_denominators_ignore_non_ru_rows(db_session: AsyncSession) -> None:
    """RIASEC now has a full `kk` set in the DB (KZ-302) plus, here, a second
    synthetic `kk` clone — the counts normalization divides by must be
    unmoved: they pin to `ru`."""
    before_riasec = await riasec_service.question_counts(db_session, AgeGroup.senior)
    before_likert = await assessment_shared.likert_total_questions(db_session, AgeGroup.senior)

    ru_questions = (
        await db_session.execute(
            select(Question).where(
                Question.instrument == QuestionInstrument.riasec, Question.locale == "ru"
            )
        )
    ).scalars().all()
    for q in ru_questions:
        db_session.add(
            Question(
                locale="kk", instrument=q.instrument, riasec_type=q.riasec_type,
                bigfive_domain=q.bigfive_domain, mi_category=q.mi_category, facet=q.facet,
                keyed=q.keyed, text=f"{q.text} (kk2)", short_text=q.short_text, icon=q.icon,
                order=q.order, age_tier=q.age_tier,
            )
        )
    await db_session.flush()

    assert await riasec_service.question_counts(db_session, AgeGroup.senior) == before_riasec
    assert await assessment_shared.likert_total_questions(db_session, AgeGroup.senior) == before_likert


async def test_structural_fields_match_between_ru_and_other_locales(
    db_session: AsyncSession,
) -> None:
    """Now non-trivial for `questions` (146 `kk` RIASEC rows); the guard
    KZ-303..306 keep relying on as they add more locales."""
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
                    f"{model.__tablename__} {key}: {attr} differs between {row.locale} and ru"
                )
