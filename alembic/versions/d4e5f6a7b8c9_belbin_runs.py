"""belbin runs (BTRSPI)

PRO-338 Ф2.3 (epic Тикеты-новые-тесты/03-Фаза2-Белбин.md). Append-only
история прохождений Belbin BTRSPI: `assessment_id` НЕ unique — повторное
прохождение = новая строка. Мирроит f3d9a1c2e6b8 (psychoemotional_runs)
structurally, но без raw `CREATE TYPE`: unlike psychoemotional_runs'
`validity_flag` (one enum-typed column), Belbin has no column that names a
single role — `role_totals` holds all 8 roles at once as one JSONB dict, so
there's nothing here for a Postgres enum to type. Role keys are owned by
the content bank (scripts/belbin_bank.py, Ф2.2), not the DB schema.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "belbin_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("assessment_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("allocations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("role_totals", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"], ["assessments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_belbin_runs_assessment_id"),
        "belbin_runs",
        ["assessment_id"],
        unique=False,  # append-only история
    )
    op.create_index(
        op.f("ix_belbin_runs_user_id"),
        "belbin_runs",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_belbin_runs_user_id"), table_name="belbin_runs"
    )
    op.drop_index(
        op.f("ix_belbin_runs_assessment_id"),
        table_name="belbin_runs",
    )
    op.drop_table("belbin_runs")
