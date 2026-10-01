"""PRO-338 Ф1.10 — add 'kondash_anxiety' QuestionInstrument member.

The `empathy_confidence` JSONB result container on analysis_results already
exists (added in a1b2c3d4e5f6, Ф0.2) and is shared with boyko_empathy
(added in b2c3d4e5f6a7, Ф1.9) — no column change needed here.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-16 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block in PostgreSQL.
    op.execute("COMMIT")
    op.execute("ALTER TYPE question_instrument_enum ADD VALUE IF NOT EXISTS 'kondash_anxiety'")


def downgrade() -> None:
    pass
    # PostgreSQL does not support removing enum values without recreating the type.
