"""add role to users

Revision ID: 12cdf8d6ab06
Revises: f2a9c6e814b7
Create Date: 2026-09-09 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "12cdf8d6ab06"
down_revision: str | None = "f2a9c6e814b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE user_role_enum AS ENUM ('student', 'admin', 'psychologist');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.Enum("student", "admin", "psychologist", name="user_role_enum", create_type=False),
            nullable=False,
            server_default="student",
        ),
    )
    op.execute("UPDATE users SET role = 'admin' WHERE is_admin = true")
    op.alter_column("users", "role", server_default=None)
    # `is_admin` is intentionally left in place, physically present but no
    # longer mapped by the model — dropped in a later cleanup migration
    # once `role` has lived in prod for a while (see app/models/user.py).
    # It needs a server default now: the model stops sending it on INSERT,
    # so without one every future insert would violate the existing NOT
    # NULL constraint.
    op.alter_column("users", "is_admin", server_default=sa.false())


def downgrade() -> None:
    op.alter_column("users", "is_admin", server_default=None)
    op.drop_column("users", "role")
    op.execute("DROP TYPE IF EXISTS user_role_enum;")
