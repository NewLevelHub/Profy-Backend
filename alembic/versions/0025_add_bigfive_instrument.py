"""add Big Five as a second question instrument alongside RIASEC

`questions` gains an `instrument` discriminator (riasec/big_five, existing
rows default to riasec) plus bigfive_domain/facet/keyed — riasec_type becomes
nullable since Big Five rows don't use it. `analysis_results` gains
big_five/thinking_style/personality_highlights to store the new report data.
No existing data is touched beyond backfilling instrument='riasec'.

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-05 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

QUESTION_INSTRUMENT_ENUM = postgresql.ENUM("riasec", "big_five", name="question_instrument_enum")
BIGFIVE_DOMAIN_ENUM = postgresql.ENUM("N", "E", "O", "A", "C", name="bigfive_domain_enum")
KEYED_ENUM = postgresql.ENUM("plus", "minus", name="keyed_enum")


def upgrade() -> None:
    QUESTION_INSTRUMENT_ENUM.create(op.get_bind())
    BIGFIVE_DOMAIN_ENUM.create(op.get_bind())
    KEYED_ENUM.create(op.get_bind())

    op.add_column(
        "questions",
        sa.Column("instrument", QUESTION_INSTRUMENT_ENUM, nullable=False, server_default="riasec"),
    )
    op.create_index("ix_questions_instrument", "questions", ["instrument"])
    op.add_column("questions", sa.Column("bigfive_domain", BIGFIVE_DOMAIN_ENUM, nullable=True))
    op.add_column("questions", sa.Column("facet", sa.Integer(), nullable=True))
    op.add_column("questions", sa.Column("keyed", KEYED_ENUM, nullable=True))
    op.alter_column("questions", "riasec_type", nullable=True)

    op.add_column(
        "analysis_results",
        sa.Column("big_five", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "analysis_results",
        sa.Column("thinking_style", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "analysis_results",
        sa.Column("personality_highlights", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("analysis_results", "personality_highlights")
    op.drop_column("analysis_results", "thinking_style")
    op.drop_column("analysis_results", "big_five")

    op.alter_column("questions", "riasec_type", nullable=False)
    op.drop_column("questions", "keyed")
    op.drop_column("questions", "facet")
    op.drop_column("questions", "bigfive_domain")
    op.drop_index("ix_questions_instrument", table_name="questions")
    op.drop_column("questions", "instrument")

    KEYED_ENUM.drop(op.get_bind())
    BIGFIVE_DOMAIN_ENUM.drop(op.get_bind())
    QUESTION_INSTRUMENT_ENUM.drop(op.get_bind())
