"""Bank-seeded content tables (`questions`, `question_pairs`,
`motivation_statements`, `directions`) — single-row
localization.

These tables used to carry one physical row per locale (KZ-301 "variant A",
`Model.locale`); that design was replaced by one row per logical item, with
localizable fields stored as `{"ru": ..., "kk": ...}` JSONB maps read via
`app.i18n.pick_locale`/`pick_locale_list` (docs/i18n-contract.md §8). This
file covers: every fully-translated table's rows carry both `ru` and `kk`
keys; display services correctly serve `kk` text (with per-row fallback to
`ru` when a `kk` key is genuinely missing); and scoring/counting reads the
single row set directly (no more "pin to `ru` so `kk` rows don't double the
denominator" — there's only one row to count).

Real transactional Postgres session (rolled back) — synthetic rows/mutations
added in a test never escape it.
"""

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import i18n
from app.models.direction import Direction
from app.models.motivation import MotivationStatement
from app.models.question import Question, QuestionInstrument
from app.models.question_pair import QuestionPair
from app.services import (
    assessment_shared,
    motivation_service,
    question_pair_service,
    question_service,
    riasec_service,
)


@pytest.fixture(autouse=True)
def _clear_fallback_counts():
    i18n.reset_fallback_counts()
    yield
    i18n.reset_fallback_counts()


@pytest.mark.parametrize(
    ("instrument", "expected"),
    [
        (QuestionInstrument.riasec, 146),
        (QuestionInstrument.big_five, 120),
    ],
)
async def test_question_bank_is_fully_translated(
    db_session: AsyncSession, instrument: QuestionInstrument, expected: int
) -> None:
    """Every question of the instrument is one row whose `text` carries both
    `ru` and genuinely different `kk` text; `short_text` is either present in
    both locales or absent entirely (never partially translated)."""
    rows = (
        await db_session.execute(select(Question).where(Question.instrument == instrument))
    ).scalars().all()

    assert len(rows) == expected
    for q in rows:
        assert q.text.get("ru") and q.text.get("kk") and q.text["ru"] != q.text["kk"]
        if q.short_text is not None:
            assert q.short_text.get("ru") and q.short_text.get("kk")


async def test_pick_locale_falls_back_per_row_when_kk_is_missing(db_session: AsyncSession) -> None:
    """Deleting one direction's `kk` translation only affects that row — every
    other direction still serves real `kk` text, and exactly one fallback is
    recorded for the missing one."""
    directions = (await db_session.execute(select(Direction))).scalars().all()
    assert len(directions) > 1
    target = next(d for d in directions if "kk" in d.name)
    target.name = {"ru": target.name["ru"]}
    await db_session.flush()

    i18n._current_locale.set("kk")
    assert i18n.pick_locale(target.name) == target.name["ru"]
    assert i18n.fallback_counts().get("kk") == 1

    other = next(d for d in directions if d.id != target.id)
    assert i18n.pick_locale(other.name) == other.name["kk"]
    assert i18n.fallback_counts().get("kk") == 1  # unchanged — no second fallback


async def test_get_all_questions_kk_serves_the_full_kk_set(db_session: AsyncSession) -> None:
    """The Likert instruments are fully translated, so a `kk`
    test is served entirely as `kk` text with no fallback."""
    all_questions = (await db_session.execute(select(Question))).scalars().all()
    by_id = {q.id: q for q in all_questions}
    i18n._current_locale.set("kk")

    questions = await question_service.get_all_questions(db_session)

    assert questions
    for q in questions:
        assert q.text == by_id[q.id].text["kk"]
    assert i18n.fallback_counts().get("kk") is None


async def test_get_pairs_kk_serves_translated_frame_and_options(
    db_session: AsyncSession,
) -> None:
    """Forced-choice pairs (ДДО) render `kk` frame + option text, and the
    pick still scores (option ids resolve to the same Question rows
    regardless of UI locale — there's only one Question row now)."""
    all_pairs = (await db_session.execute(select(QuestionPair))).scalars().all()
    ru_frames = {p.frame["ru"] for p in all_pairs if p.frame}
    i18n._current_locale.set("kk")

    pairs = await question_pair_service.get_pairs(db_session)

    assert pairs
    assert all(p.frame not in ru_frames for p in pairs)  # kk frames, not ru
    assert all(p.option_a.text and p.option_b.text for p in pairs)
    assert all(p.option_a.id != p.option_b.id for p in pairs)


async def test_directions_kk_names_and_shared_slug(db_session: AsyncSession) -> None:
    """Every direction has a `kk` name; `slug`/`holland_code` are plain
    scalars (never localized), so career matching is locale-invariant."""
    from scripts.riasec_professions import PROFESSIONS
    expected = len({p["title"] for p in PROFESSIONS})  # title-deduped bank size

    rows = (await db_session.execute(select(Direction))).scalars().all()
    assert len(rows) == expected
    for d in rows:
        assert d.name.get("kk"), f"{d.slug} has no kk name"

    # matched_careers scores on the full 6-dim profile -> same ranking whatever the locale
    profile = {"R": 10.0, "I": 90.0, "A": 10.0, "S": 10.0, "E": 10.0, "C": 80.0}
    i18n._current_locale.set("ru")
    ru_ranked = [(d.slug, s) for d, s in await riasec_service.matched_careers(profile, db_session)]
    i18n._current_locale.set("kk")
    kk_ranked = [(d.slug, s) for d, s in await riasec_service.matched_careers(profile, db_session)]
    assert ru_ranked == kk_ranked


async def test_motivation_triplets_kk(db_session: AsyncSession) -> None:
    """Motivation statements (MOST/LEAST triplets) render `kk`; category
    assignment is unchanged."""
    all_stmts_db = (await db_session.execute(select(MotivationStatement))).scalars().all()
    by_stmt_id = {s.id: s for s in all_stmts_db}
    i18n._current_locale.set("kk")

    grouped = await motivation_service.triplets(db_session)
    all_stmts = [s for stmts in grouped.values() for s in stmts]
    assert len(all_stmts) == 36
    for s in all_stmts:
        assert i18n.pick_locale(s.text) == by_stmt_id[s.id].text["kk"]


async def test_scoring_denominators_count_the_single_row_set(db_session: AsyncSession) -> None:
    """riasec_service.question_counts / assessment_shared.likert_total_questions
    read `questions` directly with no locale filter — there's one row per
    question now, so the count is simply "how many rows there are",
    independent of which locale's text happens to be requested."""
    i18n._current_locale.set("ru")
    ru_riasec = await riasec_service.question_counts(db_session)
    ru_likert = await assessment_shared.likert_total_questions(db_session)

    i18n._current_locale.set("kk")
    kk_riasec = await riasec_service.question_counts(db_session)
    kk_likert = await assessment_shared.likert_total_questions(db_session)

    assert kk_riasec == ru_riasec
    assert kk_likert == ru_likert
