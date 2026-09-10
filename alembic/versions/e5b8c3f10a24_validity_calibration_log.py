"""validity calibration log

PRO-299 (эпик PRO-282, Фаза 1). Append-only row per completed assessment
(incl. retakes) — sd_raw + carelessness indices + age_group + date, for
recalibrating `validity_thresholds.json` on our own sample later. Reuses the
existing `sd_level_enum` / `traffic_light_enum` / `age_group_enum` types.

Revision ID: e5b8c3f10a24
Revises: d4a7e21b9f30
Create Date: 2026-09-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e5b8c3f10a24'
down_revision: Union[str, None] = 'd4a7e21b9f30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SD_LEVEL_ENUM = postgresql.ENUM(
    "ok", "social_desirability", "high", name="sd_level_enum", create_type=False
)
_TRAFFIC_LIGHT_ENUM = postgresql.ENUM(
    "green", "yellow", "red", name="traffic_light_enum", create_type=False
)
_AGE_GROUP_ENUM = postgresql.ENUM(
    "junior", "middle", "senior", name="age_group_enum", create_type=False
)


def upgrade() -> None:
    op.create_table(
        "validity_calibration_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("assessment_id", sa.UUID(), nullable=False),
        sa.Column("sd_raw", sa.Integer(), nullable=False),
        sa.Column("sd_level", _SD_LEVEL_ENUM, nullable=False),
        sa.Column("longstring_max", sa.Integer(), nullable=False),
        sa.Column("irv", sa.Float(), nullable=False),
        sa.Column("infrequency_failed", sa.Integer(), nullable=False),
        sa.Column("careless_flag", sa.Boolean(), nullable=False),
        sa.Column("traffic_light", _TRAFFIC_LIGHT_ENUM, nullable=False),
        sa.Column("age_group", _AGE_GROUP_ENUM, nullable=False),
        sa.Column("thresholds_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"], ["assessments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_validity_calibration_log_assessment_id"),
        "validity_calibration_log",
        ["assessment_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_validity_calibration_log_assessment_id"),
        table_name="validity_calibration_log",
    )
    op.drop_table("validity_calibration_log")
