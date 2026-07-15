"""add parent_id, profile, label_junior, label_senior, age_min, is_leaf to directions

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-15 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive-only: existing required_scores/bonus_scores scoring keeps working
    # untouched until [GATE] AKN-021. Defaults keep every existing row valid:
    # is_leaf=true (old rows are all leaves), profile={} (no axis contribution).
    op.add_column(
        "directions",
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("directions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_directions_parent_id", "directions", ["parent_id"])
    op.add_column(
        "directions",
        sa.Column(
            "profile",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("directions", sa.Column("label_junior", sa.String(length=255), nullable=True))
    op.add_column("directions", sa.Column("label_senior", sa.String(length=255), nullable=True))
    op.add_column("directions", sa.Column("age_min", sa.Integer(), nullable=True))
    op.add_column(
        "directions",
        sa.Column("is_leaf", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("directions", "is_leaf")
    op.drop_column("directions", "age_min")
    op.drop_column("directions", "label_senior")
    op.drop_column("directions", "label_junior")
    op.drop_column("directions", "profile")
    op.drop_index("ix_directions_parent_id", table_name="directions")
    op.drop_column("directions", "parent_id")
