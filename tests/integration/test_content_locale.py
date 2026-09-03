"""KZ-301..305 — `locale` on the bank-seeded content tables.

Covers: tables with no translation yet stay `ru`-only; the question banks
(RIASEC KZ-302, Big Five KZ-303, MI KZ-304), junior/middle pairs (KZ-304) and
motivation statements + Harter pairs (KZ-305) carry `kk`; `localized_rows`
resolves the request locale per natural key and falls back to `ru` for units
the locale hasn't translated (recording a fallback); scoring denominators stay
pinned to `ru`; and structural fields match between `ru` and every other locale
of one logical row.

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
from app.services import (
    assessment_shared,
    motivation_pair_service,
    motivation_service,
    question_pair_service,
    question_service,
    riasec_service,
)
from app.services.content_locale import localized_rows

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


async def test_every_content_table_has_a_complete_kk_set(db_session: AsyncSession) -> None:
    """KZ-302..306: every bank-seeded content table now has one `kk` row per
    `ru` row (same natural key)."""
    for model, key_attrs, _ in _STRUCTURAL:
        rows = (await db_session.execute(select(model))).scalars().all()
        ru = {tuple(getattr(r, a) for a in key_attrs) for r in rows if r.locale == "ru"}
        kk = {tuple(getattr(r, a) for a in key_attrs) for r in rows if r.locale == "kk"}
        assert ru and kk == ru, f"{model.__tablename__}: kk set != ru set (missing {ru - kk})"


@pytest.mark.parametrize(
    ("instrument", "expected", "ticket"),
    [
        (QuestionInstrument.riasec, 146, "KZ-302"),
        (QuestionInstrument.big_five, 120, "KZ-303"),
        (QuestionInstrument.mi, 48, "KZ-304"),
    ],
)
async def test_question_bank_has_a_complete_kk_set(
    db_session: AsyncSession, instrument: QuestionInstrument, expected: int, ticket: str
) -> None:
    """Every question of the instrument has a `kk` row, structurally identical
    to its `ru` sibling, with genuinely different text."""
    rows = (
        await db_session.execute(select(Question).where(Question.instrument == instrument))
    ).scalars().all()
    ru = {q.order: q for q in rows if q.locale == "ru"}
    kk = {q.order: q for q in rows if q.locale == "kk"}

    assert set(kk) == set(ru) and len(kk) == expected, ticket
    for order, kk_q in kk.items():
        ru_q = ru[order]
        assert kk_q.riasec_type == ru_q.riasec_type
        assert kk_q.bigfive_domain == ru_q.bigfive_domain
        assert kk_q.facet == ru_q.facet
        assert kk_q.keyed == ru_q.keyed
        assert kk_q.age_tier == ru_q.age_tier
        assert kk_q.icon == ru_q.icon
        assert (kk_q.short_text is None) == (ru_q.short_text is None)
        assert kk_q.text and kk_q.text != ru_q.text


async def test_localized_rows_per_key_fallback_and_swap_in(db_session: AsyncSession) -> None:
    """Drop every `kk` direction row but one (within the rolled-back txn), then
    resolve under `kk`: the surviving slug comes back `kk`, the rest fall back
    to `ru`, and exactly one fallback is recorded."""
    kk_dirs = (
        await db_session.execute(select(Direction).where(Direction.locale == "kk"))
    ).scalars().all()
    assert len(kk_dirs) > 1
    kept = kk_dirs[0]
    for d in kk_dirs[1:]:
        await db_session.delete(d)
    await db_session.flush()
    i18n._current_locale.set("kk")

    rows = await localized_rows(db_session, select(Direction), Direction, key="slug")

    by_slug = {d.slug: d for d in rows}
    assert by_slug[kept.slug].locale == "kk"
    assert all(d.locale == "ru" for d in rows if d.slug != kept.slug)
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


async def test_get_all_questions_kk_serves_the_full_kk_set(db_session: AsyncSession) -> None:
    """All three Likert instruments are translated (KZ-302/303/304), so a `kk`
    senior test is served entirely as `kk` text with no fallback."""
    ru_senior = (
        await db_session.execute(
            select(func.count())
            .select_from(Question)
            .where(Question.age_tier.in_(("junior", "middle", "senior")), Question.locale == "ru")
        )
    ).scalar_one()
    ru_text = {
        (r.instrument, r.text)
        for r in (
            await db_session.execute(select(Question).where(Question.locale == "ru"))
        ).scalars()
    }
    i18n._current_locale.set("kk")

    questions = await question_service.get_all_questions(db_session, AgeGroup.senior)

    assert len(questions) == ru_senior
    assert all((q.instrument, q.text) not in ru_text for q in questions)  # every row is kk
    assert i18n.fallback_counts().get("kk") is None


async def test_get_pairs_kk_serves_translated_frame_and_options(
    db_session: AsyncSession,
) -> None:
    """KZ-304: junior forced-choice pairs render `kk` frame + option text, and
    the pick still scores (option ids resolve to the kk question rows)."""
    ru_frames = {
        p.frame
        for p in (
            await db_session.execute(
                select(QuestionPair).where(QuestionPair.locale == "ru")
            )
        ).scalars()
    }
    i18n._current_locale.set("kk")

    pairs = await question_pair_service.get_pairs(db_session, AgeGroup.junior)

    assert pairs
    assert all(p.frame not in ru_frames for p in pairs)  # kk frames
    assert all(p.option_a.text and p.option_b.text for p in pairs)
    assert all(p.option_a.id != p.option_b.id for p in pairs)


async def test_directions_kk_names_and_shared_slug(db_session: AsyncSession) -> None:
    """KZ-306: every direction has a `kk` name row; `slug` / `holland_code` are
    shared (not per-locale), so career matching is locale-invariant."""
    rows = (await db_session.execute(select(Direction))).scalars().all()
    ru = {d.slug: d for d in rows if d.locale == "ru"}
    kk = {d.slug: d for d in rows if d.locale == "kk"}

    assert set(kk) == set(ru) and len(kk) == 145
    for slug, kk_d in kk.items():
        assert kk_d.holland_code == ru[slug].holland_code
        assert kk_d.name  # non-empty kk name

    # matched_careers scores on holland_code -> same ranking whatever the locale
    code = ["I", "R", "C"]
    i18n._current_locale.set("ru")
    ru_ranked = [(d.slug, s) for d, s in await riasec_service.matched_careers(code, db_session)]
    i18n._current_locale.set("kk")
    kk_ranked = [(d.slug, s) for d, s in await riasec_service.matched_careers(code, db_session)]
    assert ru_ranked == kk_ranked


async def test_motivation_triplets_and_pairs_kk(db_session: AsyncSession) -> None:
    """KZ-305: motivation statements (senior triplets) and Harter pairs
    (junior/middle) render `kk`; category assignment is unchanged."""
    ru_stmt_text = {
        s.text
        for s in (
            await db_session.execute(
                select(MotivationStatement).where(MotivationStatement.locale == "ru")
            )
        ).scalars()
    }
    i18n._current_locale.set("kk")

    grouped = await motivation_service.triplets(db_session)
    all_stmts = [s for stmts in grouped.values() for s in stmts]
    assert len(all_stmts) == 36
    assert all(s.text not in ru_stmt_text for s in all_stmts)  # kk text
    assert all(s.locale == "kk" for s in all_stmts)

    pairs = await motivation_pair_service.pairs(db_session)
    assert len(pairs) == 18
    assert all(p.locale == "kk" and p.text_a and p.text_b for p in pairs)
    # a/b poles still map to the same single category
    assert all(p.category_a == p.category_b for p in pairs)


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
