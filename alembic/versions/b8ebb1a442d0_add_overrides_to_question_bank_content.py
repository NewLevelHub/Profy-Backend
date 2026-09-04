"""add_overrides_to_question_bank_content

Revision ID: b8ebb1a442d0
Revises: 42f3568179a9
Create Date: 2026-09-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'b8ebb1a442d0'
down_revision: Union[str, None] = '42f3568179a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = (
    "questions",
    "question_pairs",
    "motivation_statements",
    "motivation_pairs",
    "directions",
)


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("overrides", JSONB, nullable=False, server_default="{}"),
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_column(table, "overrides")
