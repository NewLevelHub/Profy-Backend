"""create profession simulations and logs

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-15 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profession_simulations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("leaf_slug", sa.String(length=100), nullable=False),
        sa.Column("steps", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_index("ix_profession_simulations_leaf_slug", "profession_simulations", ["leaf_slug"], unique=True)

    op.create_table(
        "profession_simulation_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("leaf_slug", sa.String(length=100), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_index("ix_profession_simulation_logs_assessment_id", "profession_simulation_logs", ["assessment_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_profession_simulation_logs_assessment_id", table_name="profession_simulation_logs")
    op.drop_table("profession_simulation_logs")
    op.drop_index("ix_profession_simulations_leaf_slug", table_name="profession_simulations")
    op.drop_table("profession_simulations")
