"""matched_careers needs a real DB round trip (it queries `directions`
directly), so this lives in integration/, not unit/ next to the rest of
riasec_service's pure-function tests.

Runs against the shared dev DB (tests/conftest.py — rollback-isolated, but
~90 real directions are already seeded): the two test directions use a
`test-` prefixed slug to avoid colliding with real ones, and a large
`limit` so they're guaranteed to appear in the result regardless of how the
real seeded directions happen to score against this test's profile."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.direction import Direction
from app.services import riasec_service

# Profile that shares no letters with the CCC/EEE fallback fixtures below
# (and is flat enough that Pearson against typical O*NET vectors stays
# middling) — used so the two synthetic rows can tie at the fallback floor.
_NO_OVERLAP = {"R": 10.0, "I": 10.0, "A": 10.0, "S": 10.0, "E": 10.0, "C": 10.0}


async def test_matched_careers_tie_break_is_deterministic_by_slug(
    db_session: AsyncSession,
) -> None:
    """Two directions without onet_vector and with non-overlapping Holland
    codes both score 0 against a profile that shares no letters with either
    — a genuine tie. Repeated-letter codes ("CCC"/"EEE") are used so this
    test can't accidentally collide with a real seeded direction. Inserted
    in slug-descending order — if the old score-only sort were still in
    place, Python's stable sort would just preserve that insertion order
    (zzz before aaa) instead of resolving the tie deterministically."""
    d_z = Direction(name={"ru": "Z Test Direction"}, slug="test-tiebreak-zzz", holland_code="CCC")
    d_a = Direction(name={"ru": "A Test Direction"}, slug="test-tiebreak-aaa", holland_code="EEE")
    db_session.add_all([d_z, d_a])
    await db_session.flush()

    matched = await riasec_service.matched_careers(_NO_OVERLAP, db_session, limit=1000)

    tied = [
        (d.slug, score) for d, score in matched
        if d.slug in ("test-tiebreak-aaa", "test-tiebreak-zzz")
    ]
    assert len(tied) == 2, "both test directions must appear with a limit this large"
    assert tied[0][1] == tied[1][1] == 0.0, "test setup should produce a genuine tie (no letters overlap)"
    assert [slug for slug, _ in tied] == ["test-tiebreak-aaa", "test-tiebreak-zzz"]


async def test_matched_careers_keeps_directions_that_share_an_exact_holland_code(
    db_session: AsyncSession,
) -> None:
    """Both directions sharing an exact holland_code must survive, in the
    same slug-ascending tie-break order as any other tie. A repeated-letter
    code ("CCC") keeps this isolated from the ~140 real seeded directions
    (which never repeat a letter)."""
    d_z = Direction(name={"ru": "Z Duplicate"}, slug="test-dup-zzz", holland_code="CCC")
    d_a = Direction(name={"ru": "A Duplicate"}, slug="test-dup-aaa", holland_code="CCC")
    db_session.add_all([d_z, d_a])
    await db_session.flush()

    # C-heavy profile so the CCC fallback scores above zero — ranking still
    # ties between the two duplicates.
    profile = {"R": 10.0, "I": 10.0, "A": 10.0, "S": 20.0, "E": 30.0, "C": 90.0}
    matched = await riasec_service.matched_careers(profile, db_session, limit=1000)

    dup_slugs = [d.slug for d, _ in matched if d.slug in ("test-dup-aaa", "test-dup-zzz")]
    assert dup_slugs == ["test-dup-aaa", "test-dup-zzz"], "both must survive, in slug-ascending tie-break order"


async def test_matched_careers_prefers_pearson_shape_over_code_collision(
    db_session: AsyncSession,
) -> None:
    """A Social-shaped profile must rank a Social O*NET vector above a
    Conventional one even when both directions share the same holland_code
    letters in a different order — the failure mode PRO-385 fixed."""
    social = Direction(
        name={"ru": "Test Social"},
        slug="test-pearson-social",
        holland_code="CSI",
        onet_vector={"R": 1.0, "I": 2.0, "A": 2.0, "S": 7.0, "E": 2.0, "C": 2.0},
    )
    finance = Direction(
        name={"ru": "Test Finance"},
        slug="test-pearson-finance",
        holland_code="CSI",
        onet_vector={"R": 1.0, "I": 3.0, "A": 1.0, "S": 1.0, "E": 3.0, "C": 7.0},
    )
    db_session.add_all([social, finance])
    await db_session.flush()

    # Azat-like: S dominates, C≈I in the mid band.
    profile = {
        "R": 43.3, "I": 53.0, "A": 46.9, "S": 79.1, "E": 45.8, "C": 53.1,
    }
    matched = await riasec_service.matched_careers(profile, db_session, limit=1000)
    by_slug = {d.slug: score for d, score in matched}

    assert by_slug["test-pearson-social"] > by_slug["test-pearson-finance"]
