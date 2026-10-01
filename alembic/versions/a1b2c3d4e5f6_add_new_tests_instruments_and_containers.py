"""PRO-338 Ф0.2 — add 4 new QuestionInstrument members (professional_types,
professional_types_abilities, eysenck, elers) and 4 nullable JSONB result
containers on analysis_results (professional_types, eysenck, elers,
empathy_confidence) for the specialist-only new-tests report.

Belbin and АСТУР are intentionally NOT touched here — they don't use the
Question/QuestionInstrument model at all (ipsative point-allocation /
timed-subtest formats don't fit Likert/pair), and their own result storage
is a separate table with append-only history, built in their own phase
(Ф2.3/Ф3.3 of Тикеты-новые-тесты/), not a JSONB snapshot column here.

Revision ID: a1b2c3d4e5f6
Revises: 3b2c5ba64ef1
Create Date: 2026-09-15 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "3b2c5ba64ef1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block in PostgreSQL.
    op.execute("COMMIT")
    op.execute("ALTER TYPE question_instrument_enum ADD VALUE IF NOT EXISTS 'professional_types'")
    op.execute("COMMIT")
    op.execute("ALTER TYPE question_instrument_enum ADD VALUE IF NOT EXISTS 'professional_types_abilities'")
    op.execute("COMMIT")
    op.execute("ALTER TYPE question_instrument_enum ADD VALUE IF NOT EXISTS 'eysenck'")
    op.execute("COMMIT")
    op.execute("ALTER TYPE question_instrument_enum ADD VALUE IF NOT EXISTS 'elers'")

    op.add_column("analysis_results", sa.Column("professional_types", postgresql.JSONB(), nullable=True))
    op.add_column("analysis_results", sa.Column("eysenck", postgresql.JSONB(), nullable=True))
    op.add_column("analysis_results", sa.Column("elers", postgresql.JSONB(), nullable=True))
    op.add_column("analysis_results", sa.Column("empathy_confidence", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("analysis_results", "empathy_confidence")
    op.drop_column("analysis_results", "elers")
    op.drop_column("analysis_results", "eysenck")
    op.drop_column("analysis_results", "professional_types")
    # PostgreSQL does not support removing enum values without recreating the type.
