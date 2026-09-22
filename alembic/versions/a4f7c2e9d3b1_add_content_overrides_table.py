"""add content_overrides table

PRO-424 admin content editor for ipsative/battery instruments (Belbin,
ASTUR, ...): a single `instrument`-keyed row holding the admin's full
replacement content bank per locale, read by
`app.services.admin_content_service.get_content_override` and merged in by
`astur_service.build_content` / `belbin_service.get_belbin_config` ahead of
the bank's own hardcoded default. Not to be confused with the existing
per-field `overrides` JSONB column on questions/directions/etc (see
c31a7d0b9e64) — that's a different, older admin-override mechanism keyed by
row + field, this one replaces an entire instrument's content bank.

Revision ID: a4f7c2e9d3b1
Revises: b8911a00feb0
Create Date: 2026-09-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a4f7c2e9d3b1'
down_revision: Union[str, None] = 'b8911a00feb0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "content_overrides",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("instrument", sa.String(), nullable=False),
        sa.Column("content_ru", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("content_kk", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_content_overrides_instrument"),
        "content_overrides",
        ["instrument"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_content_overrides_instrument"), table_name="content_overrides"
    )
    op.drop_table("content_overrides")
