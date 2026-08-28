"""matched_careers needs a real DB round trip (it queries `directions`
directly), so this lives in integration/, not unit/ next to the rest of
riasec_service's pure-function tests.

Runs against the shared dev DB (tests/conftest.py — rollback-isolated, but
~90 real directions are already seeded): the two test directions use a
`test-` prefixed slug to avoid colliding with real ones, and a large
`limit` so they're guaranteed to appear in the result regardless of how the
real seeded directions happen to score against this test's user_code."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.direction import Direction
from app.services import riasec_service


async def test_matched_careers_tie_break_is_deterministic_by_slug(
    db_session: AsyncSession,
) -> None:
    """Two directions with different, non-overlapping Holland codes both
    score 0 against a user_code that shares no letters with either — a
    genuine tie that dedup (below) must not remove, since the codes
    themselves aren't identical. Repeated-letter codes ("CCC"/"EEE") are used
    so this test can't accidentally collide with a real seeded direction (no
    real profession's holland_code repeats a letter). Inserted in
    slug-descending order — if the old score-only sort were still in place,
    Python's stable sort would just preserve that insertion order (zzz
    before aaa) instead of resolving the tie deterministically."""
    d_z = Direction(name="Z Test Direction", slug="test-tiebreak-zzz", holland_code="CCC")
    d_a = Direction(name="A Test Direction", slug="test-tiebreak-aaa", holland_code="EEE")
    db_session.add_all([d_z, d_a])
    await db_session.flush()

    matched = await riasec_service.matched_careers(["R", "I", "A"], db_session, limit=1000)

    tied = [
        (d.slug, score) for d, score in matched
        if d.slug in ("test-tiebreak-aaa", "test-tiebreak-zzz")
    ]
    assert len(tied) == 2, "both test directions must appear with a limit this large"
    assert tied[0][1] == tied[1][1] == 0, "test setup should produce a genuine tie (no letters overlap)"
    assert [slug for slug, _ in tied] == ["test-tiebreak-aaa", "test-tiebreak-zzz"]


async def test_matched_careers_keeps_directions_that_share_an_exact_holland_code(
    db_session: AsyncSession,
) -> None:
    """matched_careers used to drop every direction but one whenever two
    shared the exact same holland_code (found live: 3 of 5 careers shown to
    a {C,S,E}-topped student all had holland_code=="CSE") — but with the
    catalog now past 120 directions, exact-code collisions are unavoidable
    (more directions than there are distinct 3-distinct-letter codes), so
    that silently hid a growing fraction of the whole catalog from every
    student, forever. The "reads as repeating itself" problem this was
    guarding against is now handled downstream instead (see
    report_v2_assembler.build_riasec_careers's evidence-based
    differentiation) — so both should now survive, in the same
    slug-ascending tie-break order as any other tie. A repeated-letter code
    ("CCC") keeps this isolated from the ~140 real seeded directions (which
    never repeat a letter)."""
    d_z = Direction(name="Z Duplicate", slug="test-dup-zzz", holland_code="CCC")
    d_a = Direction(name="A Duplicate", slug="test-dup-aaa", holland_code="CCC")
    db_session.add_all([d_z, d_a])
    await db_session.flush()

    matched = await riasec_service.matched_careers(["C", "S", "E"], db_session, limit=1000)

    dup_slugs = [d.slug for d, _ in matched if d.slug in ("test-dup-aaa", "test-dup-zzz")]
    assert dup_slugs == ["test-dup-aaa", "test-dup-zzz"], "both must survive, in slug-ascending tie-break order"
