"""psychoemotional runs (МЦВ Собчик)

PRO-305 (эпик PRO-282, Фаза 2). Append-only история прохождений
психоэмоционального теста: `assessment_id` НЕ unique — повторное прохождение
= новая строка. Сырые выборы (2 списка по 8 ID) + тайминги + `metrics`
(JSONB, форму владеет движок PRO-309) + флаг достоверности прохождения (§B7)
+ версия порогов. Ретроспективно не создаётся.

Revision ID: f3d9a1c2e6b8
Revises: e5b8c3f10a24
Create Date: 2026-09-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f3d9a1c2e6b8'
down_revision: Union[str, None] = 'e5b8c3f10a24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VALIDITY_FLAG_ENUM = postgresql.ENUM(
    "ok", "caution", "low",
    name="psychoemotional_validity_flag_enum", create_type=False,
)


def upgrade() -> None:
    op.execute(
        "CREATE TYPE psychoemotional_validity_flag_enum AS ENUM "
        "('ok', 'caution', 'low')"
    )
    op.create_table(
        "psychoemotional_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("assessment_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("list1", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("list2", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "list1_dt_ms",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "list2_dt_ms",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("pause_actual_sec", sa.Integer(), nullable=False),
        sa.Column(
            "checkin",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("validity_flag", _VALIDITY_FLAG_ENUM, nullable=True),
        sa.Column(
            "validity_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "hint_keys",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("thresholds_version", sa.Integer(), nullable=True),
        sa.Column(
            "tech_invalid",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"], ["assessments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_psychoemotional_runs_assessment_id"),
        "psychoemotional_runs",
        ["assessment_id"],
        unique=False,  # append-only история
    )
    op.create_index(
        op.f("ix_psychoemotional_runs_user_id"),
        "psychoemotional_runs",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_psychoemotional_runs_user_id"), table_name="psychoemotional_runs"
    )
    op.drop_index(
        op.f("ix_psychoemotional_runs_assessment_id"),
        table_name="psychoemotional_runs",
    )
    op.drop_table("psychoemotional_runs")
    op.execute("DROP TYPE IF EXISTS psychoemotional_validity_flag_enum")
