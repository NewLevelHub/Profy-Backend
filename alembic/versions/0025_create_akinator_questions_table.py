"""create akinator_questions table

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-15 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Purely additive: a new table next to the old `questions`, which stays
    # untouched and keeps serving the old block-based assessment until
    # [GATE] AKN-021. No overlap in semantics or storage with `questions`.
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE akinator_question_kind_enum AS ENUM ('direct', 'situational');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE akinator_question_age_variant_enum AS ENUM ('both', 'junior', 'senior');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.create_table(
        "akinator_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(
                "direct", "situational",
                name="akinator_question_kind_enum", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column(
            "age_variant",
            postgresql.ENUM(
                "both", "junior", "senior",
                name="akinator_question_age_variant_enum", create_type=False,
            ),
            nullable=False,
            server_default="both",
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_junior", sa.Text(), nullable=True),
        sa.Column("options", postgresql.JSONB(), nullable=False),
        sa.Column("resolves_pair", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_akinator_questions_kind", "akinator_questions", ["kind"])
    op.create_index("ix_akinator_questions_is_active", "akinator_questions", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_akinator_questions_is_active", table_name="akinator_questions")
    op.drop_index("ix_akinator_questions_kind", table_name="akinator_questions")
    op.drop_table("akinator_questions")
    op.execute("DROP TYPE IF EXISTS akinator_question_age_variant_enum;")
    op.execute("DROP TYPE IF EXISTS akinator_question_kind_enum;")
