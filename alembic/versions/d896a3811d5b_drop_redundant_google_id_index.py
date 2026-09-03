"""drop_redundant_google_id_index

Revision ID: d896a3811d5b
Revises: caf6ae824d45
Create Date: 2026-08-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd896a3811d5b'
down_revision: Union[str, None] = 'caf6ae824d45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # uq_users_google_id (added in bf4109ec3b43) already builds an implicit
    # unique index backing the constraint — this explicit index on the same
    # single column is pure redundant write-path maintenance with zero query
    # benefit, mirroring the same pre-existing redundancy on users.email.
    op.drop_index("ix_users_google_id", table_name="users")


def downgrade() -> None:
    op.create_index("ix_users_google_id", "users", ["google_id"])
