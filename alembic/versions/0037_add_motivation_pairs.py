"""add motivation_pairs (Harter-format motivation for junior/middle)

New tables `motivation_pairs` (18 rows — see scripts/motivation_pair_bank.py)
and `motivation_pair_responses` (one row per assessment per answered pair:
chosen category + intensity). This is a parallel mechanism to the existing
motivation_statements/motivation_responses triplet tables, used only for
junior/middle profiles (app/services/motivation_pair_service.py); senior
keeps using the existing triplet tables unchanged. No existing data touched.

Revision ID: 0037
Revises: 0036
Create Date: 2026-08-06 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MOTIVATION_CATEGORY_ENUM = postgresql.ENUM(
    "interest", "challenge", "helping", "freedom", "money",
    "recognition", "stability", "creation", "teamwork",
    name="motivation_category_enum",
    create_type=False,  # already exists (migration 0026)
)

MOTIVATION_INTENSITY_ENUM = postgresql.ENUM(
    "high", "medium", name="motivation_intensity_enum", create_type=False,
)


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE motivation_intensity_enum AS ENUM ('high','medium'); "
        "EXCEPTION WHEN duplicate_object THEN null; END $$;"
    )

    op.create_table(
        "motivation_pairs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pair_index", sa.Integer(), nullable=False),
        sa.Column("category_a", MOTIVATION_CATEGORY_ENUM, nullable=False),
        sa.Column("category_b", MOTIVATION_CATEGORY_ENUM, nullable=False),
        sa.Column("text_a", sa.String(), nullable=False),
        sa.Column("text_b", sa.String(), nullable=False),
    )
    op.create_index("ix_motivation_pairs_pair_index", "motivation_pairs", ["pair_index"], unique=True)

    op.create_table(
        "motivation_pair_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "assessment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pair_index", sa.Integer(), nullable=False),
        sa.Column("chosen_category", MOTIVATION_CATEGORY_ENUM, nullable=False),
        sa.Column("intensity", MOTIVATION_INTENSITY_ENUM, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_motivation_pair_responses_assessment_id", "motivation_pair_responses", ["assessment_id"])
    op.create_unique_constraint(
        "uq_motivation_pair_response_assessment_pair",
        "motivation_pair_responses",
        ["assessment_id", "pair_index"],
    )


def downgrade() -> None:
    op.drop_table("motivation_pair_responses")
    op.drop_table("motivation_pairs")
    op.execute("DROP TYPE IF EXISTS motivation_intensity_enum")
