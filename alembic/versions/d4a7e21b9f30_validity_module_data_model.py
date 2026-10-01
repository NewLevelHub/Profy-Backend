"""validity module data model: validity questions + assessment_validity

PRO-297 (эпик PRO-282, Фаза 1 «Достоверность протокола»). Recommendation from
the ticket adopted: validity items are reused `questions` rows (scored through
the existing `user_response` path), not a separate table.

- `question_instrument_enum` gains `'validity'`; `questions` gains
  `validity_role` (`validity_role_enum`: sd_key | infrequency, NULL otherwise)
  and `validity_meta` (JSONB: `keyed` / `expected_answer`).
- `assessment_validity` — one computed row per assessment (traffic light +
  MC-SDS score + carelessness indices + thresholds version). Written by
  validity_service (PRO-299); NOT created retrospectively for existing
  assessments.

Revision ID: d4a7e21b9f30
Revises: c9f21d7e4a3b
Create Date: 2026-09-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd4a7e21b9f30'
down_revision: Union[str, None] = 'c9f21d7e4a3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VALIDITY_ROLE_ENUM = postgresql.ENUM(
    "sd_key", "infrequency", name="validity_role_enum", create_type=False
)
_SD_LEVEL_ENUM = postgresql.ENUM(
    "ok", "social_desirability", "high", name="sd_level_enum", create_type=False
)
_TRAFFIC_LIGHT_ENUM = postgresql.ENUM(
    "green", "yellow", "red", name="traffic_light_enum", create_type=False
)


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block (same as
    # 0038 for 'mi'). The new value is not used elsewhere in this migration.
    op.execute("COMMIT")
    op.execute(
        "ALTER TYPE question_instrument_enum ADD VALUE IF NOT EXISTS 'validity'"
    )

    op.execute("CREATE TYPE validity_role_enum AS ENUM ('sd_key', 'infrequency')")
    op.execute(
        "CREATE TYPE sd_level_enum AS ENUM ('ok', 'social_desirability', 'high')"
    )
    op.execute("CREATE TYPE traffic_light_enum AS ENUM ('green', 'yellow', 'red')")

    # --- questions: validity items reuse this table (ticket recommendation) ---
    op.add_column(
        "questions",
        sa.Column("validity_role", _VALIDITY_ROLE_ENUM, nullable=True),
    )
    op.add_column(
        "questions",
        sa.Column(
            "validity_meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # --- assessment_validity: computed verdict, one row per assessment ---
    op.create_table(
        "assessment_validity",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("assessment_id", sa.UUID(), nullable=False),
        sa.Column("sd_raw", sa.Integer(), nullable=False),
        sa.Column("sd_level", _SD_LEVEL_ENUM, nullable=False),
        sa.Column("longstring_max", sa.Integer(), nullable=False),
        sa.Column("irv", sa.Float(), nullable=False),
        sa.Column("infrequency_failed", sa.Integer(), nullable=False),
        sa.Column(
            "careless_flag",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("traffic_light", _TRAFFIC_LIGHT_ENUM, nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("rt_ms", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("thresholds_version", sa.Integer(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sd_raw >= 0 AND sd_raw <= 20",
            name="ck_assessment_validity_sd_raw_range",
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"], ["assessments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "assessment_id", name="uq_assessment_validity_assessment_id"
        ),
    )
    op.create_index(
        op.f("ix_assessment_validity_assessment_id"),
        "assessment_validity",
        ["assessment_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_assessment_validity_assessment_id"),
        table_name="assessment_validity",
    )
    op.drop_table("assessment_validity")

    op.drop_column("questions", "validity_meta")
    op.drop_column("questions", "validity_role")

    op.execute("DROP TYPE IF EXISTS traffic_light_enum")
    op.execute("DROP TYPE IF EXISTS sd_level_enum")
    op.execute("DROP TYPE IF EXISTS validity_role_enum")
    # question_instrument_enum keeps its 'validity' value — PostgreSQL cannot
    # drop an enum value without recreating the type (same as 0038 for 'mi').
