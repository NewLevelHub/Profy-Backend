"""add university favorites table

Revision ID: a1c5f39be702
Revises: f2a9c6e814b7
Create Date: 2026-09-07

PRO-265. A student can star a university; starred universities are listed
first both in the standalone catalogue and in the direction-scoped program
picker.

The unique (user_id, university_id) constraint is what makes starring
idempotent — the service leans on it via ON CONFLICT DO NOTHING instead of
a racy SELECT-then-INSERT. Both FKs cascade: the user side is what
scripts/delete_user.py already relies on, and a star pointing at a deleted
university is meaningless.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1c5f39be702"
down_revision: Union[str, None] = "f2a9c6e814b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "university_favorites",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("university_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["university_id"], ["universities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "university_id", name="uq_university_favorites_user_university"
        ),
    )
    op.create_index(
        op.f("ix_university_favorites_user_id"), "university_favorites", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_university_favorites_university_id"),
        "university_favorites",
        ["university_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_university_favorites_university_id"), table_name="university_favorites")
    op.drop_index(op.f("ix_university_favorites_user_id"), table_name="university_favorites")
    op.drop_table("university_favorites")
