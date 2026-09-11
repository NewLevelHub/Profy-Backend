"""drop psychoemotional_runs.hint_keys — specialist hint texts removed

Product decision: the report's psychoemotional section goes to a licensed
psychologist, who doesn't need canned research-derived phrasing and could
find it confusing. The whole hint catalog/assembly (hints.py,
psychoemotional_hints.json) is removed along with the column that stored
which keys had been assigned to a run.

Revision ID: c8d2e6a1f470
Revises: b7e3a5f9c1d4
Create Date: 2026-09-11 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c8d2e6a1f470"
down_revision: Union[str, None] = "b7e3a5f9c1d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("psychoemotional_runs", "hint_keys")


def downgrade() -> None:
    op.add_column(
        "psychoemotional_runs",
        sa.Column(
            "hint_keys",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
