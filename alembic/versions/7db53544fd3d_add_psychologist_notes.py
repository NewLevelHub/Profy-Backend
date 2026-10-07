"""add psychologist_notes table

Revision ID: 7db53544fd3d
Revises: 12cdf8d6ab06
Create Date: 2026-09-09 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7db53544fd3d"
down_revision: str | None = "12cdf8d6ab06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "psychologist_notes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("psychologist_id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["psychologist_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_psychologist_notes_psychologist_id"),
        "psychologist_notes",
        ["psychologist_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_psychologist_notes_student_id"),
        "psychologist_notes",
        ["student_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_psychologist_notes_student_id"),
        table_name="psychologist_notes",
    )
    op.drop_index(
        op.f("ix_psychologist_notes_psychologist_id"),
        table_name="psychologist_notes",
    )
    op.drop_table("psychologist_notes")
