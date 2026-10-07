"""astur_runs.subtest_started_at

PRO-338 Ф3.4 (epic Тикеты-новые-тесты/04-Фаза3-АСТУР.md) — timer engine.
`{subtest_key: ISO timestamp}` recorded by `POST .../subtest/{n}/start`,
consumed by the submit endpoint to compute real server-observed elapsed
time per subtest, never a client-reported duration. Not part of Ф3.3's
original astur_runs shape — that ticket's scope was the raw-data/scoring
split, timing is Ф3.4's own addition.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-16 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "astur_runs",
        sa.Column(
            "subtest_started_at",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("astur_runs", "subtest_started_at")
