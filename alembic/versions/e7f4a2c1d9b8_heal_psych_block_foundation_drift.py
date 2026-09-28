"""heal psych_block_foundation drift: consents + analysis_results.psychoemotional

`c9f21d7e4a3b` (psych_block_foundation) is far back in this chain, before the
dev database's recorded `alembic_version` — Alembic will never re-run it.
Investigating the "did not become ready" CD failures (2026-09-25) turned up
that dev's actual schema only got part of that revision applied (`users.role`
/ `user_role_enum` exist), while `consents` and
`analysis_results.psychoemotional` never landed — the same kind of
branch-switch drift already worked around in `e4ed44aa0d52`, `c8d2e6a1f470`
and `b8911a00feb0`. `alembic upgrade head` alone can't fix a gap this far
back in history, so this is a forward-only repair step: idempotent, and a
no-op on any database where `c9f21d7e4a3b` ran in full (prod, a fresh DB).

Revision ID: e7f4a2c1d9b8
Revises: a7c3e1f9b2d4
Create Date: 2026-09-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e7f4a2c1d9b8"
down_revision: Union[str, None] = "a7c3e1f9b2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    analysis_results_columns = {c["name"] for c in inspector.get_columns("analysis_results")}
    if "psychoemotional" not in analysis_results_columns:
        op.add_column(
            "analysis_results",
            sa.Column("psychoemotional", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )

    if not inspector.has_table("consents"):
        op.create_table(
            "consents",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("signed_by", sa.String(length=255), nullable=False),
            sa.Column(
                "scope", sa.String(length=64), nullable=False, server_default="psych_block"
            ),
            sa.Column("assessment_id", sa.UUID(), nullable=True),
            sa.Column(
                "signed_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["assessment_id"], ["assessments.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_consents_user_id"), "consents", ["user_id"], unique=False
        )
        op.create_index(
            op.f("ix_consents_assessment_id"), "consents", ["assessment_id"], unique=False
        )


def downgrade() -> None:
    # No-op: this is a forward-only repair for databases that were missing
    # structure `c9f21d7e4a3b` should already have created. Downgrading would
    # drop `consents`/`psychoemotional` even on databases where
    # `c9f21d7e4a3b` legitimately owns them (prod, a fresh DB).
    pass
