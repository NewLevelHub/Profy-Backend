"""add motivation block (forced-choice triplets)

New tables `motivation_statements` (36 rows, 12 triplets x 3 statements,
seeded by scripts/seed_motivation_statements.py) and `motivation_responses`
(one row per assessment per answered triplet: most/least statement picked).
`analysis_results` gains motivation/motivation_top/motivation_highlights to
store the scored report data. No existing data is touched.

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-05 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MOTIVATION_CATEGORY_ENUM = postgresql.ENUM(
    "interest", "challenge", "helping", "freedom", "money",
    "recognition", "stability", "creation", "teamwork",
    name="motivation_category_enum",
    create_type=False,  # created explicitly below (idempotent raw SQL) —
    # op.create_table()'s automatic enum-creation double-fires CREATE TYPE
    # for standalone ENUM objects in this SQLAlchemy/asyncpg combination.
)


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE motivation_category_enum AS ENUM "
        "('interest','challenge','helping','freedom','money',"
        "'recognition','stability','creation','teamwork'); "
        "EXCEPTION WHEN duplicate_object THEN null; END $$;"
    )

    op.create_table(
        "motivation_statements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("triplet_index", sa.Integer(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("category", MOTIVATION_CATEGORY_ENUM, nullable=False),
        sa.Column("text", sa.String(), nullable=False),
    )
    op.create_index("ix_motivation_statements_triplet_index", "motivation_statements", ["triplet_index"])
    op.create_index("ix_motivation_statements_category", "motivation_statements", ["category"])

    op.create_table(
        "motivation_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "assessment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("triplet_index", sa.Integer(), nullable=False),
        sa.Column(
            "most_statement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("motivation_statements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "least_statement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("motivation_statements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_motivation_responses_assessment_id", "motivation_responses", ["assessment_id"])
    op.create_unique_constraint(
        "uq_motivation_response_assessment_triplet",
        "motivation_responses",
        ["assessment_id", "triplet_index"],
    )

    op.add_column(
        "analysis_results",
        sa.Column("motivation", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "analysis_results",
        sa.Column("motivation_top", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "analysis_results",
        sa.Column("motivation_highlights", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("analysis_results", "motivation_highlights")
    op.drop_column("analysis_results", "motivation_top")
    op.drop_column("analysis_results", "motivation")

    op.drop_table("motivation_responses")
    op.drop_table("motivation_statements")
    op.execute("DROP TYPE IF EXISTS motivation_category_enum")
