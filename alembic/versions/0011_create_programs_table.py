"""create programs table

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-24 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "programs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("university_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("direction_slug", sa.String(100), nullable=False),
        sa.Column("language", sa.String(50), nullable=False),
        sa.Column("cost_per_year", sa.Numeric(12, 2), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("who_its_for", sa.Text, nullable=True),
        sa.Column(
            "career_options",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "requirements",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "deadlines",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "grants",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["university_id"], ["universities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_programs_university_id", "programs", ["university_id"])
    op.create_index("ix_programs_direction_slug", "programs", ["direction_slug"])


def downgrade() -> None:
    op.drop_index("ix_programs_direction_slug", table_name="programs")
    op.drop_index("ix_programs_university_id", table_name="programs")
    op.drop_table("programs")
