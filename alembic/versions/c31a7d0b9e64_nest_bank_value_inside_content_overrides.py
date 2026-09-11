"""nest bank_value inside content overrides

Question-bank overrides used to store the admin's value directly
(`{"text": "новый текст"}`). They now store what was replaced alongside it
(`{"text": {"value": "новый текст", "bank_value": "текст из банка"}}`), so a
revert can put the row back immediately instead of waiting for the next
deploy's resync — see app/services/admin_lock.py and
docs/admin-backend-requests-pro-242.md §4.

Rows converted here get no `bank_value` key at all: those overrides were
written before the original was recorded anywhere. The key's absence — not a
null — is what means "unknown", because several overridable columns are
themselves nullable. Clearing such an override still drops it; the following
seed run is what restores the bank's own value.

Revision ID: c31a7d0b9e64
Revises: f2a9c6e814b7
"""
from alembic import op

revision = "c31a7d0b9e64"
down_revision = "f2a9c6e814b7"
branch_labels = None
depends_on = None

_TABLES = (
    "questions",
    "question_pairs",
    "motivation_statements",
    "motivation_pairs",
    "directions",
)

# Idempotent per entry: an entry already in the nested shape is left alone,
# so re-running over a partially converted table cannot double-wrap it.
_UPGRADE = """
UPDATE {table}
SET overrides = (
    SELECT jsonb_object_agg(
        key,
        CASE
            WHEN jsonb_typeof(value) = 'object' AND value ? 'value' THEN value
            ELSE jsonb_build_object('value', value)
        END
    )
    FROM jsonb_each(overrides)
)
WHERE overrides <> '{{}}'::jsonb
"""

_DOWNGRADE = """
UPDATE {table}
SET overrides = (
    SELECT jsonb_object_agg(
        key,
        CASE
            WHEN jsonb_typeof(value) = 'object' AND value ? 'value' THEN value -> 'value'
            ELSE value
        END
    )
    FROM jsonb_each(overrides)
)
WHERE overrides <> '{{}}'::jsonb
"""


def upgrade() -> None:
    for table in _TABLES:
        op.execute(_UPGRADE.format(table=table))


def downgrade() -> None:
    for table in _TABLES:
        op.execute(_DOWNGRADE.format(table=table))
