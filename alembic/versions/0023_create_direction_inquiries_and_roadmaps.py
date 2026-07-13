"""create direction_inquiries and direction_roadmaps, add selected_direction_slug

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-13 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assessments",
        sa.Column("selected_direction_slug", sa.String(length=100), nullable=True),
    )

    op.create_table(
        "direction_inquiries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "assessment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("direction_slug", sa.String(length=100), nullable=False),
        sa.Column("questions", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("answers", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("readiness", sa.String(length=50), nullable=False),
        sa.Column("fit_summary", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("assessment_id", "direction_slug", name="uq_inquiry_assessment_direction"),
    )
    op.create_index(
        "ix_direction_inquiries_assessment_id", "direction_inquiries", ["assessment_id"]
    )

    op.create_table(
        "direction_roadmaps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "assessment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("direction_slug", sa.String(length=100), nullable=False),
        sa.Column("direction_name", sa.String(length=255), nullable=False),
        sa.Column("target", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("growth_focus", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("stages", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("skills_to_build", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("subjects_to_focus", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("university_track", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("assessment_id", "direction_slug", name="uq_roadmap_assessment_direction"),
    )
    op.create_index(
        "ix_direction_roadmaps_assessment_id", "direction_roadmaps", ["assessment_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_direction_roadmaps_assessment_id", table_name="direction_roadmaps")
    op.drop_table("direction_roadmaps")
    op.drop_index("ix_direction_inquiries_assessment_id", table_name="direction_inquiries")
    op.drop_table("direction_inquiries")
    op.drop_column("assessments", "selected_direction_slug")
