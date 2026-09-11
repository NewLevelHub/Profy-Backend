"""add *_i18n override columns to universities / programs

Revision ID: b2d6f0a3c1e8
Revises: a1c5e9d2b7f4
Create Date: 2026-09-04 15:00:00.000000

KZ-501 — the university/program catalog stores one Russian string per free-text
field (`University.description`, `Program.description`, `Program.who_its_for`).
This adds a nullable sibling JSONB column to each (`{"kk": "..."}`) that holds
only non-`ru` translations; the `ru` text stays in the base column and is never
duplicated. The columns are filled incrementally by KZ-504's batch translation.
Until then they are empty and the read side falls back to the base column, so
this migration changes no API response.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b2d6f0a3c1e8"
down_revision: Union[str, None] = "a1c5e9d2b7f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column("universities", sa.Column("description_i18n", _JSONB, nullable=True))
    op.add_column("programs", sa.Column("description_i18n", _JSONB, nullable=True))
    op.add_column("programs", sa.Column("who_its_for_i18n", _JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("programs", "who_its_for_i18n")
    op.drop_column("programs", "description_i18n")
    op.drop_column("universities", "description_i18n")
