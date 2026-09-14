"""add last_active_at to users

The admin users list had only `created_at` to describe a user's activity, so
the "ACTIVITY" column was really a registration date — and there was no way to
answer "who started a diagnostic and never came back"
(docs/admin-backend-requests-pro-242.md §5, §6).

Existing rows are backfilled from the newest thing they are known to have
done: their latest assessment, or their latest answer within one. That is a
floor, not the true last visit — nothing before this migration recorded plain
browsing — but it beats leaving every pre-existing user indistinguishable from
one who has never been seen at all.

Revision ID: d47e8c105b23
Revises: c31a7d0b9e64
"""
import sqlalchemy as sa
from alembic import op

revision = "d47e8c105b23"
down_revision = "c31a7d0b9e64"
branch_labels = None
depends_on = None

_BACKFILL = """
WITH activity AS (
    SELECT p.user_id AS user_id, MAX(a.created_at) AS ts
    FROM profiles p
    JOIN assessments a ON a.profile_id = p.id
    GROUP BY p.user_id

    UNION ALL

    SELECT p.user_id AS user_id, MAX(r.created_at) AS ts
    FROM profiles p
    JOIN assessments a ON a.profile_id = p.id
    JOIN user_responses r ON r.assessment_id = a.id
    GROUP BY p.user_id
)
UPDATE users u
SET last_active_at = agg.ts
FROM (SELECT user_id, MAX(ts) AS ts FROM activity GROUP BY user_id) agg
WHERE agg.user_id = u.id
"""


def upgrade() -> None:
    op.add_column("users", sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_last_active_at", "users", ["last_active_at"])
    op.execute(_BACKFILL)


def downgrade() -> None:
    op.drop_index("ix_users_last_active_at", table_name="users")
    op.drop_column("users", "last_active_at")
