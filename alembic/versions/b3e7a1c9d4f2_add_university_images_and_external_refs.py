"""add university_images, university_external_refs, program source_category

Revision ID: b3e7a1c9d4f2
Revises: ad95fcc5d772
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b3e7a1c9d4f2'
down_revision: Union[str, None] = 'ad95fcc5d772'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "university_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("university_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["university_id"], ["universities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_university_images_university_id", "university_images", ["university_id"])
    op.create_unique_constraint(
        "uq_university_images_university_checksum",
        "university_images",
        ["university_id", "checksum_sha256"],
    )
    # At most one primary photo per university — enforced at the DB level
    # since this table is written by an unattended batch script, not just
    # app code with a model-level check.
    op.create_index(
        "uq_university_images_one_primary",
        "university_images",
        ["university_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )

    op.create_table(
        "university_external_refs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("external_name", sa.Text(), nullable=True),
        sa.Column("university_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_method", sa.String(20), nullable=True),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["university_id"], ["universities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_university_external_refs_university_id", "university_external_refs", ["university_id"])
    op.create_unique_constraint(
        "uq_university_external_refs_source_external_id",
        "university_external_refs",
        ["source", "external_id"],
    )

    op.add_column("programs", sa.Column("source_category", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("programs", "source_category")

    op.drop_constraint(
        "uq_university_external_refs_source_external_id", "university_external_refs", type_="unique"
    )
    op.drop_index("ix_university_external_refs_university_id", table_name="university_external_refs")
    op.drop_table("university_external_refs")

    op.drop_index("uq_university_images_one_primary", table_name="university_images")
    op.drop_constraint("uq_university_images_university_checksum", "university_images", type_="unique")
    op.drop_index("ix_university_images_university_id", table_name="university_images")
    op.drop_table("university_images")
