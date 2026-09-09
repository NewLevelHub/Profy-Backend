"""add psychologist_student_assignments table

Revision ID: e4ed44aa0d52
Revises: 12cdf8d6ab06
Create Date: 2026-09-09 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4ed44aa0d52"
down_revision: str | None = "12cdf8d6ab06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "psychologist_student_assignments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("psychologist_id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
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
        sa.UniqueConstraint(
            "psychologist_id",
            "student_id",
            name="uq_psychologist_student_assignments_pair",
        ),
    )
    op.create_index(
        op.f("ix_psychologist_student_assignments_psychologist_id"),
        "psychologist_student_assignments",
        ["psychologist_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_psychologist_student_assignments_student_id"),
        "psychologist_student_assignments",
        ["student_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_psychologist_student_assignments_student_id"),
        table_name="psychologist_student_assignments",
    )
    op.drop_index(
        op.f("ix_psychologist_student_assignments_psychologist_id"),
        table_name="psychologist_student_assignments",
    )
    op.drop_table("psychologist_student_assignments")
