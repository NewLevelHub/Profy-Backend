"""add users.locale

Revision ID: d80fbf5d1f43
Revises: caf6ae824d45
Create Date: 2026-09-02 14:25:21.613737

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd80fbf5d1f43'
down_revision: Union[str, None] = 'caf6ae824d45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # UI locale of the user. Distinct from profiles.language ("language of
    # instruction"). Enum holds both values from the start; "kk" only becomes a
    # runtime-honored locale in the KZ-603 enable PR (no feature flag).
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE locale_enum AS ENUM ('ru', 'kk');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.add_column(
        "users",
        sa.Column(
            "locale",
            postgresql.ENUM("ru", "kk", name="locale_enum", create_type=False),
            nullable=False,
            server_default="ru",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "locale")
    op.execute("DROP TYPE IF EXISTS locale_enum")
