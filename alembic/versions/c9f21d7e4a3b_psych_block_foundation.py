"""psych block foundation: users.role, analysis_results psych containers, consents

PRO-291 (эпик PRO-282). Adds the structural seams for the psychology block:
- `users.role` — lightweight enum, задел под PRO-321. Nothing enforces
  access on it yet; existing admins are backfilled to `role='admin'`.
- `analysis_results.validity` / `.psychoemotional` — JSONB containers, NULL
  until the matching phase computes them. Kept off `summary`/narrative on
  purpose so PRO-321 stays a one-liner.
- `consents` — records parental/guardian consent (scope `psych_block`).
  Non-blocking in the MVP; the report sections carry a `consent_ok` flag.

Revision ID: c9f21d7e4a3b
Revises: f2a9c6e814b7
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c9f21d7e4a3b'
down_revision: Union[str, None] = 'f2a9c6e814b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_USER_ROLE_ENUM = postgresql.ENUM(
    "user", "staff", "psychologist", "admin",
    name="user_role_enum", create_type=False,
)


def upgrade() -> None:
    # --- users.role — задел под PRO-321 (роль «Психолог»); пока ничем не
    # ограничивает доступ, is_admin остаётся источником истины. ---
    op.execute(
        "CREATE TYPE user_role_enum AS ENUM "
        "('user', 'staff', 'psychologist', 'admin')"
    )
    op.add_column(
        "users",
        sa.Column("role", _USER_ROLE_ENUM, nullable=False, server_default="user"),
    )
    op.execute("UPDATE users SET role = 'admin' WHERE is_admin IS TRUE")

    # --- analysis_results: структурно-отделимые контейнеры выводов
    # психоблока (НЕ в summary/нарративе). NULL до расчёта своей фазы. ---
    op.add_column(
        "analysis_results",
        sa.Column("validity", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "analysis_results",
        sa.Column(
            "psychoemotional", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )

    # --- consents: факт согласия родителя/законного представителя.
    # Не блокирует показ (MVP) — фиксируется для будущего. ---
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
    op.drop_index(op.f("ix_consents_assessment_id"), table_name="consents")
    op.drop_index(op.f("ix_consents_user_id"), table_name="consents")
    op.drop_table("consents")

    op.drop_column("analysis_results", "psychoemotional")
    op.drop_column("analysis_results", "validity")

    op.drop_column("users", "role")
    op.execute("DROP TYPE IF EXISTS user_role_enum")
