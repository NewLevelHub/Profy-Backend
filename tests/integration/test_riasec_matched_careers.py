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
    """Two directions with an identical Holland code tie on match_score.
    Inserted in slug-descending order — if the old score-only sort were
    still in place, Python's stable sort would just preserve that insertion
    order (zzz before aaa) instead of resolving the tie deterministically."""
    d_z = Direction(name="Z Test Direction", slug="test-tiebreak-zzz", holland_code="RIA")
    d_a = Direction(name="A Test Direction", slug="test-tiebreak-aaa", holland_code="RIA")
    db_session.add_all([d_z, d_a])
    await db_session.flush()

    matched = await riasec_service.matched_careers(["R", "I", "A"], db_session, limit=1000)

    tied = [
        (d.slug, score) for d, score in matched
        if d.slug in ("test-tiebreak-aaa", "test-tiebreak-zzz")
    ]
    assert len(tied) == 2, "both test directions must appear with a limit this large"
    assert tied[0][1] == tied[1][1], "test setup should produce a genuine tie"
    assert [slug for slug, _ in tied] == ["test-tiebreak-aaa", "test-tiebreak-zzz"]
