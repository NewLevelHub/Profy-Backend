"""PRO-338 Ф1.9 — add 'boyko_empathy' QuestionInstrument member.

The `empathy_confidence` JSONB result container on analysis_results already
exists (added in a1b2c3d4e5f6, Ф0.2) — this instrument shares it with the
future Kondash/Prikhozhan content (Ф1.10), so no column change needed here.

Revision ID: b2c3d4e5f6a7
Revises: 2e88f631a853
Create Date: 2026-09-16 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "2e88f631a853"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block in PostgreSQL.
    op.execute("COMMIT")
    op.execute("ALTER TYPE question_instrument_enum ADD VALUE IF NOT EXISTS 'boyko_empathy'")


def downgrade() -> None:
    pass
    # PostgreSQL does not support removing enum values without recreating the type.
