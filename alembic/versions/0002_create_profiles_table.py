"""create profiles table

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-22 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE age_group_enum AS ENUM ('junior', 'middle', 'senior');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column("grade", sa.Integer(), nullable=False),
        sa.Column("city", sa.String(255), nullable=False),
        sa.Column("country", sa.String(255), nullable=False),
        sa.Column("language", sa.String(50), nullable=False),
        sa.Column("subjects_liked", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("subjects_disliked", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("subjects_easy", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("subjects_hard", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "age_group",
            postgresql.ENUM("junior", "middle", "senior", name="age_group_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("profiles")
    op.execute("DROP TYPE IF EXISTS age_group_enum;")
