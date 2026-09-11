"""МАК data model: mac_cards, mac_exercises, mac_sessions, mac_responses,
mac_notes, mac_summaries (PRO-314)

Revision ID: a4c8f19e6d2b
Revises: 7db53544fd3d
Create Date: 2026-09-11 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a4c8f19e6d2b"
down_revision: Union[str, None] = "7db53544fd3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CARD_KIND = postgresql.ENUM(
    "abstract", "scenic", "portrait", name="mac_card_kind_enum", create_type=False
)
_DRAW_MODE = postgresql.ENUM(
    "blind", "open", name="mac_draw_mode_enum", create_type=False
)
_FILLED_BY = postgresql.ENUM(
    "client", "parent", name="mac_filled_by_enum", create_type=False
)


def upgrade() -> None:
    op.execute("CREATE TYPE mac_card_kind_enum AS ENUM ('abstract', 'scenic', 'portrait')")
    op.execute("CREATE TYPE mac_draw_mode_enum AS ENUM ('blind', 'open')")
    op.execute("CREATE TYPE mac_filled_by_enum AS ENUM ('client', 'parent')")

    op.create_table(
        "mac_cards",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("image_path", sa.String(length=255), nullable=False),
        sa.Column("kind", _CARD_KIND, nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("license", sa.String(length=120), nullable=True),
        sa.Column("attribution", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("image_path"),
    )

    op.create_table(
        "mac_exercises",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("stimulus_question", sa.String(length=500), nullable=False),
        sa.Column("draw_mode", _DRAW_MODE, nullable=False),
        sa.Column("spread_size", sa.Integer(), nullable=True),
        sa.Column("pick_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("followup_questions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("subjects", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "mac_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("assessment_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("consent_id", sa.UUID(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["consent_id"], ["consents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mac_sessions_assessment_id", "mac_sessions", ["assessment_id"])
    op.create_index("ix_mac_sessions_user_id", "mac_sessions", ["user_id"])

    op.create_table(
        "mac_responses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("exercise_id", sa.UUID(), nullable=False),
        sa.Column("subject", sa.String(length=32), nullable=True),
        sa.Column("filled_by", _FILLED_BY, server_default="client", nullable=False),
        sa.Column("card_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("followup_answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("time_spent_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("revision_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["mac_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exercise_id"], ["mac_exercises.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mac_responses_session_id", "mac_responses", ["session_id"])

    op.create_table(
        "mac_notes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("response_id", sa.UUID(), nullable=True),
        sa.Column("text", sa.String(length=2000), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["mac_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["response_id"], ["mac_responses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mac_notes_session_id", "mac_notes", ["session_id"])

    op.create_table(
        "mac_summaries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("text", sa.String(length=4000), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["mac_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mac_summaries_session_id", "mac_summaries", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_mac_summaries_session_id", table_name="mac_summaries")
    op.drop_table("mac_summaries")
    op.drop_index("ix_mac_notes_session_id", table_name="mac_notes")
    op.drop_table("mac_notes")
    op.drop_index("ix_mac_responses_session_id", table_name="mac_responses")
    op.drop_table("mac_responses")
    op.drop_index("ix_mac_sessions_user_id", table_name="mac_sessions")
    op.drop_index("ix_mac_sessions_assessment_id", table_name="mac_sessions")
    op.drop_table("mac_sessions")
    op.drop_table("mac_exercises")
    op.drop_table("mac_cards")
    op.execute("DROP TYPE IF EXISTS mac_filled_by_enum")
    op.execute("DROP TYPE IF EXISTS mac_draw_mode_enum")
    op.execute("DROP TYPE IF EXISTS mac_card_kind_enum")
