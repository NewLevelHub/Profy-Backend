"""replace legacy 24-axis block quiz with RIASEC (Holland Codes) engine

Full-stack cutover: questions become single-type Likert items (riasec_type
instead of block/age_group/options), user_responses store a raw 1-5 value,
directions carry a holland_code instead of required_scores/bonus_scores, and
analysis_results store the RIASEC report shape (profile/code/meta/careers/
strengths/weaknesses/development_plan) instead of interests_map/thinking_style/
motivation/wellbeing_zones. See TICKET-riasec-migration.md and the approved
implementation plan for full context.

Old data in questions/user_responses/assessments/analysis_results/directions
is meaningless under the new model (different question bank, different
direction catalog) — truncated as part of this migration. Confirmed safe:
working branch is fresh off `main`, not production.

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-04 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HOLLAND_TYPE_ENUM = postgresql.ENUM("R", "I", "A", "S", "E", "C", name="holland_type_enum")


def upgrade() -> None:
    # Old rows are meaningless under the new question bank / direction catalog —
    # CASCADE also clears direction_inquiries/direction_roadmaps/roadmaps via
    # their assessment_id FK.
    op.execute(
        "TRUNCATE TABLE questions, user_responses, assessments, "
        "analysis_results, directions RESTART IDENTITY CASCADE"
    )

    # ── questions: block/age_group/options → riasec_type ──────────────────────
    op.drop_column("questions", "options")
    op.drop_column("questions", "age_group")
    op.drop_column("questions", "block")
    op.execute("DROP TYPE IF EXISTS question_block_enum")

    HOLLAND_TYPE_ENUM.create(op.get_bind())
    op.add_column(
        "questions",
        sa.Column("riasec_type", HOLLAND_TYPE_ENUM, nullable=False),
    )
    op.create_index("ix_questions_riasec_type", "questions", ["riasec_type"])

    # ── user_responses: selected_option_index/scores → answer_value ───────────
    op.drop_column("user_responses", "scores")
    op.drop_column("user_responses", "selected_option_index")
    op.add_column(
        "user_responses",
        sa.Column("answer_value", sa.Integer(), nullable=False),
    )
    op.create_unique_constraint(
        "uq_user_response_assessment_question",
        "user_responses",
        ["assessment_id", "question_id"],
    )

    # ── assessments: drop current_block ────────────────────────────────────────
    op.drop_column("assessments", "current_block")

    # ── directions: required_scores/bonus_scores/age_groups → holland_code ────
    op.drop_column("directions", "bonus_scores")
    op.drop_column("directions", "required_scores")
    op.drop_column("directions", "age_groups")
    op.add_column(
        "directions",
        sa.Column("holland_code", sa.String(length=3), nullable=False),
    )
    op.create_index("ix_directions_holland_code", "directions", ["holland_code"])

    # ── analysis_results: interests_map/thinking_style/motivation/wellbeing_zones
    #    → profile/code/meta/weaknesses/development_plan; directions → careers ─
    op.drop_column("analysis_results", "wellbeing_zones")
    op.drop_column("analysis_results", "motivation")
    op.drop_column("analysis_results", "thinking_style")
    op.drop_column("analysis_results", "interests_map")
    op.alter_column("analysis_results", "directions", new_column_name="careers")
    op.add_column(
        "analysis_results",
        sa.Column("profile", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "analysis_results",
        sa.Column("code", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "analysis_results",
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "analysis_results",
        sa.Column("weaknesses", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "analysis_results",
        sa.Column("development_plan", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("analysis_results", "development_plan")
    op.drop_column("analysis_results", "weaknesses")
    op.drop_column("analysis_results", "meta")
    op.drop_column("analysis_results", "code")
    op.drop_column("analysis_results", "profile")
    op.alter_column("analysis_results", "careers", new_column_name="directions")
    op.add_column("analysis_results", sa.Column("interests_map", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("analysis_results", sa.Column("thinking_style", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("analysis_results", sa.Column("motivation", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("analysis_results", sa.Column("wellbeing_zones", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))

    op.drop_index("ix_directions_holland_code", table_name="directions")
    op.drop_column("directions", "holland_code")
    op.add_column("directions", sa.Column("age_groups", postgresql.JSONB(), nullable=False, server_default=sa.text('\'["senior"]\'::jsonb')))
    op.add_column("directions", sa.Column("required_scores", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("directions", sa.Column("bonus_scores", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))

    op.add_column("assessments", sa.Column("current_block", sa.Integer(), nullable=False, server_default="0"))

    op.drop_constraint("uq_user_response_assessment_question", "user_responses", type_="unique")
    op.drop_column("user_responses", "answer_value")
    op.add_column("user_responses", sa.Column("selected_option_index", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_responses", sa.Column("scores", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))

    op.drop_index("ix_questions_riasec_type", table_name="questions")
    op.drop_column("questions", "riasec_type")
    HOLLAND_TYPE_ENUM.drop(op.get_bind())

    question_block_enum = postgresql.ENUM(
        "interests", "thinking", "personality", "motivation", "academic",
        "directions", "goal_clarification", "university", "wellbeing",
        name="question_block_enum",
    )
    question_block_enum.create(op.get_bind())
    op.add_column("questions", sa.Column("block", question_block_enum, nullable=False))
    op.add_column("questions", sa.Column("age_group", sa.Enum(name="age_group_enum", create_type=False), nullable=False))
    op.add_column("questions", sa.Column("options", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.create_index("ix_questions_block", "questions", ["block"])
    op.create_index("ix_questions_age_group", "questions", ["age_group"])
    op.create_index("ix_questions_block_age_group", "questions", ["block", "age_group"])
