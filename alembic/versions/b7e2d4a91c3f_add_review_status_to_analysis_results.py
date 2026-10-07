"""add review_status to analysis_results + analysis_result_review_edits

Psychologist review gate (docs/psychologist-review-gate-plan.md, §1).
Every row that exists before this migration was already shown to its
student, so the backfill marks all of them `published` — the gate only
applies to reports generated after it ships.

Revision ID: b7e2d4a91c3f
Revises: ab5271e14fae
Create Date: 2026-09-14 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7e2d4a91c3f"
down_revision: str | None = "ab5271e14fae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE analysis_result_review_status_enum AS ENUM ('pending_review', 'published');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)

    op.create_table(
        "analysis_result_review_edits",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("analysis_result_id", sa.UUID(), nullable=False),
        sa.Column("editor_id", sa.UUID(), nullable=True),
        sa.Column(
            "edited_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("changed_fields", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_result_id"], ["analysis_results.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["editor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_analysis_result_review_edits_analysis_result_id"),
        "analysis_result_review_edits",
        ["analysis_result_id"],
        unique=False,
    )

    op.add_column(
        "analysis_results",
        sa.Column(
            "review_status",
            sa.Enum(
                "pending_review",
                "published",
                name="analysis_result_review_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="pending_review",
        ),
    )
    op.add_column(
        "analysis_results",
        sa.Column(
            "personality_notes_override",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column("analysis_results", sa.Column("reviewed_by", sa.UUID(), nullable=True))
    op.add_column(
        "analysis_results", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("analysis_results", sa.Column("published_by", sa.UUID(), nullable=True))
    op.add_column(
        "analysis_results", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "analysis_results_reviewed_by_fkey",
        "analysis_results",
        "users",
        ["reviewed_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "analysis_results_published_by_fkey",
        "analysis_results",
        "users",
        ["published_by"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute("""
        UPDATE analysis_results
        SET review_status = 'published', published_at = created_at
        WHERE review_status = 'pending_review'
    """)

    # Partial index: both review queues scan for pending rows only, and that
    # set stays small while published rows accumulate forever.
    op.create_index(
        "ix_analysis_results_pending_review",
        "analysis_results",
        ["created_at"],
        postgresql_where=sa.text("review_status = 'pending_review'"),
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_results_pending_review", table_name="analysis_results")
    op.drop_constraint("analysis_results_published_by_fkey", "analysis_results", type_="foreignkey")
    op.drop_constraint("analysis_results_reviewed_by_fkey", "analysis_results", type_="foreignkey")
    op.drop_column("analysis_results", "published_at")
    op.drop_column("analysis_results", "published_by")
    op.drop_column("analysis_results", "reviewed_at")
    op.drop_column("analysis_results", "reviewed_by")
    op.drop_column("analysis_results", "review_status")
    op.drop_column("analysis_results", "personality_notes_override")
    op.drop_index(
        op.f("ix_analysis_result_review_edits_analysis_result_id"),
        table_name="analysis_result_review_edits",
    )
    op.drop_table("analysis_result_review_edits")
    op.execute("DROP TYPE IF EXISTS analysis_result_review_status_enum;")
