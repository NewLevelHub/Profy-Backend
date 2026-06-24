"""create roadmaps table

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-24 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "roadmaps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "assessment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessments.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("goal", sa.String(50), nullable=False),
        sa.Column("milestones", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_roadmaps_assessment_id", "roadmaps", ["assessment_id"])


def downgrade() -> None:
    op.drop_index("ix_roadmaps_assessment_id", table_name="roadmaps")
    op.drop_table("roadmaps")
