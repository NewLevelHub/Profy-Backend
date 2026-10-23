"""drop personal slot state

«Занято (личное)» is dropped (decision of 21.10): the specialist marks only
free time; everything else is closed. A closed slot has no row, so personal
rows are deleted, and personal intervals leave the week templates.

Revision ID: f206e493c0c9
Revises: 53e3c776ffd0
Create Date: 2026-10-21 09:31:36.204854

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f206e493c0c9'
down_revision: Union[str, None] = '53e3c776ffd0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM specialist_slots WHERE state = 'personal'")
    op.execute(
        """
        UPDATE specialist_week_templates
        SET days = (
            SELECT jsonb_object_agg(
                d.key,
                COALESCE(
                    (SELECT jsonb_agg(i) FROM jsonb_array_elements(d.value) AS i WHERE i->>'state' <> 'personal'),
                    '[]'::jsonb
                )
            )
            FROM jsonb_each(days) AS d
        )
        WHERE days::text LIKE '%"personal"%'
        """
    )


def downgrade() -> None:
    # The personal marks are gone for good; closed is what they become.
    pass
