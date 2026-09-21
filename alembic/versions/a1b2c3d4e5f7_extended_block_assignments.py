"""extended block assignments (Belbin/АСТУР)

PRO-338 post-Ф4.1 follow-up: a psychologist's decision to make Belbin/АСТУР
available to a student, replacing the raw hand-delivered link (Ф2.6/Ф3.6's
original "launch only from the psychologist cabinet" — the student had no
way to discover the block themselves). One row per (assessment_id, block),
not append-only — see the model's own docstring for why completion is
derived from belbin_runs/astur_runs rather than tracked here.

Revision ID: a1b2c3d4e5f7
Revises: f6a7b8c9d0e1
Create Date: 2026-09-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_EXTENDED_BLOCK_ENUM = postgresql.ENUM(
    "belbin", "astur",
    name="extended_block_enum", create_type=False,
)


def upgrade() -> None:
    op.execute("CREATE TYPE extended_block_enum AS ENUM ('belbin', 'astur')")
    op.create_table(
        "extended_block_assignments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("assessment_id", sa.UUID(), nullable=False),
        sa.Column("block", _EXTENDED_BLOCK_ENUM, nullable=False),
        sa.Column("psychologist_id", sa.UUID(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"], ["assessments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["psychologist_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_id", "block", name="uq_extended_block_assignment"),
    )
    op.create_index(
        op.f("ix_extended_block_assignments_assessment_id"),
        "extended_block_assignments",
        ["assessment_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_extended_block_assignments_assessment_id"),
        table_name="extended_block_assignments",
    )
    op.drop_table("extended_block_assignments")
    op.execute("DROP TYPE IF EXISTS extended_block_enum")
