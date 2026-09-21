"""add onet_vector to directions for Pearson career matching (PRO-385)

Revision ID: c8a3f1e92b4d
Revises: ab5271e14fae
Create Date: 2026-09-17 15:20:00.000000

Stores the full 6-dimensional O*NET RIASEC interest vector per profession so
`riasec_service.matched_careers` can rank by Pearson correlation instead of
the unstable 3-letter code. Nullable: the three catalog entries without a
US SOC analogue (Военный / Дипломат / Госслужащий) keep NULL and fall back
to the legacy positional code score.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c8a3f1e92b4d"
down_revision: Union[str, None] = "ab5271e14fae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "directions",
        sa.Column("onet_vector", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("directions", "onet_vector")
