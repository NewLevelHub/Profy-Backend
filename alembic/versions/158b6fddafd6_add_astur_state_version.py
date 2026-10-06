"""add astur state version

Revision ID: 158b6fddafd6
Revises: 405be3f3603e
Create Date: 2026-10-06 09:59:50.000935

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '158b6fddafd6'
down_revision: Union[str, None] = '405be3f3603e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "astur_runs",
        sa.Column("state_version", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("astur_runs", "state_version")
