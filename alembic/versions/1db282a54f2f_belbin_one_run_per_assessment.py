"""belbin_one_run_per_assessment

One Belbin run per assessment: a student retakes the whole diagnostic (a new
assessment), never Belbin alone. Older duplicate runs left by the former
retake path are deleted first, keeping the latest one — the run every report
already read. Autogenerate also listed the pre-existing drift from
alembic/known_schema_drift.txt — left out.

Revision ID: 1db282a54f2f
Revises: 93038740a7a3
Create Date: 2026-10-02 05:10:03.736062

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1db282a54f2f'
down_revision: Union[str, None] = '93038740a7a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM belbin_runs
        WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (
                    PARTITION BY assessment_id ORDER BY created_at DESC, id DESC
                ) AS position
                FROM belbin_runs
            ) ranked
            WHERE position > 1
        )
        """
    )
    op.drop_index(op.f('ix_belbin_runs_assessment_id'), table_name='belbin_runs')
    op.create_index(op.f('ix_belbin_runs_assessment_id'), 'belbin_runs', ['assessment_id'], unique=True)


def downgrade() -> None:
    # The deleted duplicate runs are not restored.
    op.drop_index(op.f('ix_belbin_runs_assessment_id'), table_name='belbin_runs')
    op.create_index(op.f('ix_belbin_runs_assessment_id'), 'belbin_runs', ['assessment_id'], unique=False)
