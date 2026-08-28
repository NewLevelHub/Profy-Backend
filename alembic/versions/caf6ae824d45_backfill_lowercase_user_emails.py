"""backfill_lowercase_user_emails

Revision ID: caf6ae824d45
Revises: fa81fa8a82f9
Create Date: 2026-08-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'caf6ae824d45'
down_revision: Union[str, None] = 'fa81fa8a82f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Lowercase every stored email so it matches the NormalizedEmail
    request-boundary validator added in app/schemas/auth.py — without this,
    a pre-existing mixed-case row can never be found again by login(),
    password reset, or Google account linking, since all of those now
    compare against a lowercased input.

    Row-by-row with a collision check rather than a single UPDATE: two
    case-variant rows for the "same" address (e.g. 'A@x.com' and 'a@x.com')
    may already both exist, since nothing enforced case-insensitive
    uniqueness before this. Colliding rows are left untouched and printed
    so they can be resolved by hand — merging accounts isn't something a
    migration should decide unsupervised.
    """
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, email FROM users WHERE email <> LOWER(email)")
    ).fetchall()

    skipped: list[str] = []
    for row in rows:
        lowered = row.email.lower()
        collision = conn.execute(
            sa.text("SELECT 1 FROM users WHERE email = :lowered AND id <> :id"),
            {"lowered": lowered, "id": row.id},
        ).fetchone()
        if collision:
            skipped.append(row.email)
            continue
        conn.execute(
            sa.text("UPDATE users SET email = :lowered WHERE id = :id"),
            {"lowered": lowered, "id": row.id},
        )

    if skipped:
        print(
            f"backfill_lowercase_user_emails: skipped {len(skipped)} row(s) "
            f"with a case-variant collision, needs manual resolution: {skipped}"
        )


def downgrade() -> None:
    # Original casing isn't retained anywhere, so this can't be reversed.
    pass
