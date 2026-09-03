"""add_google_oauth_fields_to_users

Revision ID: bf4109ec3b43
Revises: a06b39fb621e
Create Date: 2026-08-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bf4109ec3b43'
down_revision: Union[str, None] = 'a06b39fb621e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("users", "hashed_password", existing_type=sa.String(255), nullable=True)
    op.add_column("users", sa.Column("google_id", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_users_google_id", "users", ["google_id"])
    op.create_index("ix_users_google_id", "users", ["google_id"])


def downgrade() -> None:
    op.drop_index("ix_users_google_id", table_name="users")
    op.drop_constraint("uq_users_google_id", "users", type_="unique")
    op.drop_column("users", "google_id")

    # Google-only accounts (created after upgrade()) have no password, so
    # re-adding the NOT NULL constraint below would fail once any such
    # account exists. There's nothing meaningful to restore it to since the
    # original password was never set — mark these rows with an unusable
    # placeholder so the column can be made NOT NULL again; the account is
    # already unreachable via password login post-downgrade since the
    # google_id column dropped above is gone too.
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE users SET hashed_password = 'google-oauth-only:no-password-set' "
            "WHERE hashed_password IS NULL"
        )
    )
    op.alter_column("users", "hashed_password", existing_type=sa.String(255), nullable=False)
