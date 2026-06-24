"""add cascade delete on assessments.profile_id

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-24 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("assessments_profile_id_fkey", "assessments", type_="foreignkey")
    op.create_foreign_key(
        "assessments_profile_id_fkey",
        "assessments", "profiles",
        ["profile_id"], ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("assessments_profile_id_fkey", "assessments", type_="foreignkey")
    op.create_foreign_key(
        "assessments_profile_id_fkey",
        "assessments", "profiles",
        ["profile_id"], ["id"],
    )
