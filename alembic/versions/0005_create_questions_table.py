"""create questions table

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-22 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE question_block_enum AS ENUM (
                'interests', 'thinking', 'personality', 'motivation',
                'academic', 'directions', 'goal_clarification', 'university'
            );
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.create_table(
        "questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "block",
            postgresql.ENUM(
                "interests", "thinking", "personality", "motivation",
                "academic", "directions", "goal_clarification", "university",
                name="question_block_enum", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "age_group",
            postgresql.ENUM("junior", "middle", "senior", name="age_group_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_questions_block", "questions", ["block"])
    op.create_index("ix_questions_age_group", "questions", ["age_group"])
    op.create_index("ix_questions_block_age_group", "questions", ["block", "age_group"])


def downgrade() -> None:
    op.drop_index("ix_questions_block_age_group", table_name="questions")
    op.drop_index("ix_questions_age_group", table_name="questions")
    op.drop_index("ix_questions_block", table_name="questions")
    op.drop_table("questions")
    op.execute("DROP TYPE IF EXISTS question_block_enum;")
