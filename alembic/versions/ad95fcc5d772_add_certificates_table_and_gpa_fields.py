"""add certificates table and gpa fields

Revision ID: ad95fcc5d772
Revises: a06b39fb621e
Create Date: 2026-08-25 06:42:16.196369

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'ad95fcc5d772'
down_revision: Union[str, None] = 'a06b39fb621e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CERTIFICATE_TYPES = ("ielts", "unt", "sat", "toefl")
_GPA_SCALES = ("4", "5", "10", "100")


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE certificate_type_enum AS ENUM ('ielts', 'unt', 'sat', 'toefl');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE gpa_scale_enum AS ENUM ('4', '5', '10', '100');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.create_table(
        "certificates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM(*_CERTIFICATE_TYPES, name="certificate_type_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_certificates_profile_id", "certificates", ["profile_id"])

    op.add_column("profiles", sa.Column("gpa_value", sa.Float(), nullable=True))
    op.add_column(
        "profiles",
        sa.Column(
            "gpa_scale",
            postgresql.ENUM(*_GPA_SCALES, name="gpa_scale_enum", create_type=False),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("profiles", "gpa_scale")
    op.drop_column("profiles", "gpa_value")
    op.drop_index("ix_certificates_profile_id", table_name="certificates")
    op.drop_table("certificates")
    op.execute("DROP TYPE IF EXISTS gpa_scale_enum;")
    op.execute("DROP TYPE IF EXISTS certificate_type_enum;")
