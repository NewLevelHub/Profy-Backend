"""astur runs (АСТУР)

PRO-338 Ф3.3 (epic Тикеты-новые-тесты/04-Фаза3-АСТУР.md). Append-only
история прохождений АСТУР: `assessment_id` НЕ unique — повторное
прохождение = новая строка. Мирроит d4e5f6a7b8c9 (belbin_runs)
structurally, no raw `CREATE TYPE` needed here either — subtest/role keys
are owned by the content bank (scripts/astur_bank.py, Ф3.2), not the DB
schema, same reasoning as belbin_runs' role_totals.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-16 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "astur_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("assessment_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("subtest_timings_ms", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("lability_answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("lability_first_half_accuracy", sa.Float(), nullable=True),
        sa.Column("lability_second_half_accuracy", sa.Float(), nullable=True),
        sa.Column("raw_score", sa.Integer(), nullable=True),
        sa.Column("subtest_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("spn_group", sa.Integer(), nullable=True),
        sa.Column("recommended_profile", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        op.f("ix_astur_runs_assessment_id"),
        "astur_runs",
        ["assessment_id"],
        unique=False,  # append-only история
    )
    op.create_index(
        op.f("ix_astur_runs_user_id"),
        "astur_runs",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_astur_runs_user_id"), table_name="astur_runs"
    )
    op.drop_index(
        op.f("ix_astur_runs_assessment_id"),
        table_name="astur_runs",
    )
    op.drop_table("astur_runs")
