"""create artifacts table

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-22 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ARTIFACT_TYPES = (
    "hobby", "club", "sport", "achievement", "goal",
    "book", "game", "topic", "profession", "university", "dream",
)


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE artifact_type_enum AS ENUM (
                'hobby', 'club', 'sport', 'achievement', 'goal',
                'book', 'game', 'topic', 'profession', 'university', 'dream'
            );
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM(*_ARTIFACT_TYPES, name="artifact_type_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_artifacts_profile_id", "artifacts", ["profile_id"])


def downgrade() -> None:
    op.drop_index("ix_artifacts_profile_id", table_name="artifacts")
    op.drop_table("artifacts")
    op.execute("DROP TYPE IF EXISTS artifact_type_enum;")
