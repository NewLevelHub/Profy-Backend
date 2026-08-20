"""Add program_id to direction_roadmaps

Lets a direction roadmap remember which specific Program it was built for
(goal="university" only — null for every other goal). Needed so re-generating
for a different program of the same direction doesn't silently keep serving
the first program's plan, and so the UI can show which program the plan is
for. Nullable, ON DELETE SET NULL — losing the program reference must not
delete the roadmap itself.

Revision ID: a3f9c1d84e02
Revises: 737ff08c158c
Create Date: 2026-08-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a3f9c1d84e02'
down_revision: Union[str, None] = '737ff08c158c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'direction_roadmaps',
        sa.Column('program_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_direction_roadmaps_program_id',
        'direction_roadmaps',
        'programs',
        ['program_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_direction_roadmaps_program_id', 'direction_roadmaps', type_='foreignkey')
    op.drop_column('direction_roadmaps', 'program_id')
