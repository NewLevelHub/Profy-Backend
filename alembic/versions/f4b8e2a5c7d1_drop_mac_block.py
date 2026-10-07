"""Drop the МАК block entirely (feature removed, PRO-282 §4 scope cut)

The MAC data model (mac_cards, mac_exercises, mac_sessions, mac_responses,
mac_notes, mac_summaries — originally added by a4c8f19e6d2b /
b7e3a5f9c1d4) has been removed from the codebase: no model, router, schema,
service or seed script references these tables anymore. Those two migration
files were deleted rather than kept as dead history, and this repo's chain
was relinked around them (see down_revision below) — this migration exists
only to drop the physical tables/types on any database that already ran
them. `IF EXISTS` throughout: a no-op on a fresh database that never had
MAC in its history at all.

Revision ID: f4b8e2a5c7d1
Revises: c8d2e6a1f470
Create Date: 2026-09-14 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f4b8e2a5c7d1"
down_revision: Union[str, None] = "c8d2e6a1f470"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mac_summaries CASCADE")
    op.execute("DROP TABLE IF EXISTS mac_notes CASCADE")
    op.execute("DROP TABLE IF EXISTS mac_responses CASCADE")
    op.execute("DROP TABLE IF EXISTS mac_sessions CASCADE")
    op.execute("DROP TABLE IF EXISTS mac_exercises CASCADE")
    op.execute("DROP TABLE IF EXISTS mac_cards CASCADE")
    op.execute("DROP TYPE IF EXISTS mac_filled_by_enum")
    op.execute("DROP TYPE IF EXISTS mac_draw_mode_enum")
    op.execute("DROP TYPE IF EXISTS mac_card_kind_enum")


def downgrade() -> None:
    # Feature removed on purpose — nothing to restore. Recreating the МАК
    # tables would require the deleted a4c8f19e6d2b/b7e3a5f9c1d4 DDL, which
    # is gone; if the block ever comes back it should be a fresh model.
    pass
