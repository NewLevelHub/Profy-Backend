"""drop psychoemotional_runs.hint_keys — specialist hint texts removed

Product decision: the report's psychoemotional section goes to a licensed
psychologist, who doesn't need canned research-derived phrasing and could
find it confusing. The whole hint catalog/assembly (hints.py,
psychoemotional_hints.json) is removed along with the column that stored
which keys had been assigned to a run.

Revision ID: c8d2e6a1f470
Revises: b7e3a5f9c1d4
Create Date: 2026-09-11 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c8d2e6a1f470"
down_revision: Union[str, None] = "7db53544fd3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_runs_table_without_hint_keys() -> None:
    """Recreate `psychoemotional_runs` in the shape this revision and
    `4be92fb3b21d` (list2/list2_dt_ms/pause_actual_sec nullable) leave it in —
    for databases that lost the table to a branch-switch downgrade while
    `alembic_version` still claims `f3d9a1c2e6b8` was applied."""
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE psychoemotional_validity_flag_enum AS ENUM ('ok', 'caution', 'low'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.create_table(
        "psychoemotional_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("assessment_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("list1", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("list2", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("list1_dt_ms", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("list2_dt_ms", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=True),
        sa.Column("pause_actual_sec", sa.Integer(), nullable=True),
        sa.Column("checkin", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column(
            "validity_flag",
            postgresql.ENUM("ok", "caution", "low", name="psychoemotional_validity_flag_enum", create_type=False),
            nullable=True,
        ),
        sa.Column("validity_reasons", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("thresholds_version", sa.Integer(), nullable=True),
        sa.Column("tech_invalid", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_psychoemotional_runs_assessment_id"), "psychoemotional_runs", ["assessment_id"], unique=False)
    op.create_index(op.f("ix_psychoemotional_runs_user_id"), "psychoemotional_runs", ["user_id"], unique=False)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("psychoemotional_runs"):
        _create_runs_table_without_hint_keys()
        return
    if "hint_keys" in {c["name"] for c in inspector.get_columns("psychoemotional_runs")}:
        op.drop_column("psychoemotional_runs", "hint_keys")


def downgrade() -> None:
    op.add_column(
        "psychoemotional_runs",
        sa.Column(
            "hint_keys",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
