"""PRO-425: drop the roadmap, direction inquiry, goal overlay, the MI instrument,
Harter motivation pairs and question age tiers.

The product is 14-18 only (one battery for everyone) and has no roadmap.
There are no real users on prod, so data is dropped, not migrated.

- tables: roadmaps, direction_roadmaps, direction_inquiries, goal_overlays,
  motivation_pairs, motivation_pair_responses
- rows: MI questions (their user_responses go with them via ON DELETE
  CASCADE) and the retired junior/middle RIASEC/Big Five question pairs
  (only the ДДО pairs, instrument professional_types, stay)
- columns: questions.age_tier, questions.mi_category, question_pairs.age_tier,
  motivation_statements.text_junior, assessments.selected_direction_slug
- enum types: mi_type_enum, motivation_intensity_enum, motivation_pair_side_enum

`mi` stays a value of question_instrument_enum: Postgres cannot drop an enum
value without recreating the type, and nothing writes it any more.
age_group_enum stays (profiles.age_group).

Downgrade restores the schema (empty tables, nullable/defaulted columns), not
the data.

Revision ID: d4a7c2e9f1b3
Revises: b1c2d3e4f5a6
Create Date: 2026-09-24
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4a7c2e9f1b3"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None

_MI_TYPES = ("verbal", "logical", "musical", "visual", "bodily", "interpersonal", "intrapersonal", "naturalistic")


def upgrade() -> None:
    op.execute("DELETE FROM question_pairs WHERE instrument IN ('riasec', 'big_five')")
    op.execute("DELETE FROM questions WHERE instrument = 'mi'")

    op.drop_table("motivation_pair_responses")
    op.drop_table("motivation_pairs")
    op.drop_table("goal_overlays")
    op.drop_table("direction_inquiries")
    op.drop_table("direction_roadmaps")
    op.drop_table("roadmaps")

    op.drop_index("ix_questions_age_tier", table_name="questions")
    op.drop_column("questions", "age_tier")
    op.drop_column("questions", "mi_category")
    op.drop_index("ix_question_pairs_age_tier", table_name="question_pairs")
    op.drop_column("question_pairs", "age_tier")
    op.drop_column("motivation_statements", "text_junior")
    op.drop_column("assessments", "selected_direction_slug")

    op.execute("DROP TYPE IF EXISTS mi_type_enum")
    op.execute("DROP TYPE IF EXISTS motivation_intensity_enum")
    op.execute("DROP TYPE IF EXISTS motivation_pair_side_enum")


def downgrade() -> None:
    mi_type = postgresql.ENUM(*_MI_TYPES, name="mi_type_enum")
    intensity = postgresql.ENUM("high", "medium", name="motivation_intensity_enum")
    side = postgresql.ENUM("a", "b", name="motivation_pair_side_enum")
    for enum_type in (mi_type, intensity, side):
        enum_type.create(op.get_bind(), checkfirst=True)

    age_group = postgresql.ENUM("junior", "middle", "senior", name="age_group_enum", create_type=False)
    category = postgresql.ENUM(name="motivation_category_enum", create_type=False)
    goal = postgresql.ENUM(name="assessment_goal_enum", create_type=False)

    op.add_column("assessments", sa.Column("selected_direction_slug", sa.String(100), nullable=True))
    op.add_column("motivation_statements", sa.Column("text_junior", postgresql.JSONB(), nullable=True))
    op.add_column(
        "question_pairs",
        sa.Column("age_tier", age_group, nullable=False, server_default="senior"),
    )
    op.create_index("ix_question_pairs_age_tier", "question_pairs", ["age_tier"])
    op.add_column(
        "questions",
        sa.Column("mi_category", postgresql.ENUM(name="mi_type_enum", create_type=False), nullable=True),
    )
    op.add_column(
        "questions",
        sa.Column("age_tier", age_group, nullable=False, server_default="senior"),
    )
    op.create_index("ix_questions_age_tier", "questions", ["age_tier"])

    op.create_table(
        "roadmaps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("goal", sa.String(50), nullable=False),
        sa.Column("milestones", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("focus_summary", sa.String(1000), nullable=True),
        sa.Column("recommended_paths", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("additional_resources", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.create_index("ix_roadmaps_assessment_id", "roadmaps", ["assessment_id"], unique=True)

    op.create_table(
        "direction_roadmaps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction_slug", sa.String(100), nullable=False),
        sa.Column("direction_name", sa.String(255), nullable=False),
        sa.Column("target", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("growth_focus", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("stages", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("skills_to_build", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("subjects_to_focus", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("university_track", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("university_requirements", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("program_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("programs.id", ondelete="SET NULL", name="fk_direction_roadmaps_program_id"),
                  nullable=True),
        sa.Column("additional_resources", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("program_fit", postgresql.JSONB(), nullable=True),
        sa.UniqueConstraint("assessment_id", "direction_slug", name="uq_roadmap_assessment_direction"),
    )
    op.create_index("ix_direction_roadmaps_assessment_id", "direction_roadmaps", ["assessment_id"])
    op.create_index("ix_direction_roadmaps_program_id", "direction_roadmaps", ["program_id"])

    op.create_table(
        "direction_inquiries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction_slug", sa.String(100), nullable=False),
        sa.Column("questions", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("answers", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("readiness", sa.String(50), nullable=False),
        sa.Column("fit_summary", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("assessment_id", "direction_slug", name="uq_inquiry_assessment_direction"),
    )
    op.create_index("ix_direction_inquiries_assessment_id", "direction_inquiries", ["assessment_id"])

    op.create_table(
        "goal_overlays",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("goal", goal, nullable=False),
        sa.Column("scenario", sa.String(10), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("assessment_id", "goal", name="uq_goal_overlay_assessment_goal"),
    )
    op.create_index("ix_goal_overlays_assessment_id", "goal_overlays", ["assessment_id"])

    op.create_table(
        "motivation_pairs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pair_index", sa.Integer(), nullable=False),
        sa.Column("category_a", category, nullable=False),
        sa.Column("category_b", category, nullable=False),
        sa.Column("overrides", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("text_a", postgresql.JSONB(), nullable=False),
        sa.Column("text_b", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("pair_index", name="uq_motivation_pairs_pair_index"),
    )
    op.create_index("ix_motivation_pairs_pair_index", "motivation_pairs", ["pair_index"])

    op.create_table(
        "motivation_pair_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pair_index", sa.Integer(), nullable=False),
        sa.Column("chosen_category", category, nullable=False),
        sa.Column("intensity", postgresql.ENUM(name="motivation_intensity_enum", create_type=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("chosen_side", postgresql.ENUM(name="motivation_pair_side_enum", create_type=False),
                  nullable=False),
        sa.UniqueConstraint("assessment_id", "pair_index", name="uq_motivation_pair_response_assessment_pair"),
    )
    op.create_index("ix_motivation_pair_responses_assessment_id", "motivation_pair_responses", ["assessment_id"])
